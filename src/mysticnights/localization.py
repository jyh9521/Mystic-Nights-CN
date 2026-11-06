"""Small, explicitly scoped localization build, independent of target locale."""
from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path

from .catalogues import read_project
from .executable import patch_strings as patch_executable
from .font import build_font, decode_text, encode_text
from .resources import parse_res
from .scripts import extract_strings, patch_strings
from .typography import validate_text


def load_catalogue(path: Path) -> dict:
    catalogue = json.loads(path.read_text(encoding="utf-8"))
    if catalogue.get("format") == "localization-catalogue":
        catalogue = read_project(path)
    if catalogue.get("profile") not in {"poc", "partial", "full-text"}:
        raise ValueError("Unknown localization build profile")
    entries = catalogue.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Translation catalogue is empty")
    seen = set()
    physical_fields = set()
    for row in entries:
        if row["id"] in seen:
            raise ValueError(f"Duplicate translation ID: {row['id']}")
        seen.add(row["id"])
        if row.get("kind") not in {"elf", "script"} or row.get("role") != "display":
            raise ValueError(f"Unreviewed edit kind or role: {row['id']}")
        if (not isinstance(row.get("resource"), str)
                or type(row.get("offset")) is not int or row["offset"] < 0
                or type(row.get("capacity")) is not int or row["capacity"] < 1):
            raise ValueError(f"Invalid source location: {row['id']}")
        if row["kind"] == "script":
            if not isinstance(row.get("member"), str):
                raise ValueError(f"Missing script member: {row['id']}")
            script_id = f"{row['member']}@{row['offset']:08x}"
            if row.get("script_id") != script_id:
                raise ValueError(f"Non-canonical script ID: {row['id']}")
            canonical_id = f"{row['resource']}:{script_id}"
            physical = (row["resource"], row["member"], row["offset"])
        else:
            canonical_id = f"{row['resource']}@{row['offset']:08x}"
            physical = (row["resource"], None, row["offset"])
        if physical in physical_fields:
            raise ValueError(f"Duplicate physical field: {row['id']}")
        physical_fields.add(physical)
        if row["id"] != canonical_id:
            raise ValueError(f"Non-canonical translation ID: {row['id']}")
        if row.get("status") not in {"draft", "reviewed"}:
            raise ValueError(f"Invalid translation status: {row['id']}")
        if row.get("text_type") not in {"ui_label", "system_message", "item_description", "dialogue", "cutscene", "document"}:
            raise ValueError(f"Missing or unknown text type: {row['id']}")
        if not isinstance(row.get("target"), str) or not row["target"].strip():
            raise ValueError(f"Missing translation: {row['id']}")
        if not isinstance(row.get("source"), str) or not row["source"]:
            raise ValueError(f"Missing original source: {row['id']}")
    return catalogue


def retained_codes(image, elf_recipe: dict) -> set[int]:
    """Protect codes still used by the finite source-text survey in a partial build."""
    result = set()
    def add(text):
        for char in text:
            encoded = char.encode("cp949")
            if len(encoded) == 2:
                result.add(int.from_bytes(encoded, "big"))
    for row in elf_recipe["entries"]:
        add(row["source"])
    for name in sorted(image.files):
        if name.endswith(".RES"):
            resource = parse_res(image.read(name))
            for member in resource.entries:
                if member.name.endswith(".SCR"):
                    for row in extract_strings(resource.read(member), member.name):
                        add(row.source)
    return result


def localized_resources(image, catalogue: dict, config: dict, font_spec: dict,
                        font_path: Path, elf_recipe: dict, *, version: dict | None = None,
                        name_targets=None, plaintext_replacements=None, additional_font_texts=()):
    """Build equal-sized replacement payloads; do not write any disc files."""
    additional_font_texts = tuple(additional_font_texts)
    entries = catalogue["entries"]
    for row in entries:
        validate_text(row["target"], row.get("text_type", ""), config.get("punctuation", {}))
    for text in additional_font_texts:
        validate_text(text, "cutscene", config.get("punctuation", {}))
    original_font = parse_res(image.read("RES/SYSTEM.RES"))
    fnt = original_font.read("FONT.FNT")
    textures = {f"FONT_{n}.TM2": original_font.read(f"FONT_{n}.TM2") for n in range(1, 9)}
    protection_policy = config.get("font_protection", "poc-source-text")
    if protection_policy == "retained-display-text":
        if version is None or catalogue["profile"] != "full-text":
            raise ValueError("Retained-display protection requires a verified full-text profile")
        from .font_usage import collect_full_protected_codes
        protected, _usage_report = collect_full_protected_codes(
            image.path, version, entries, name_targets=name_targets,
            plaintext_replacements=plaintext_replacements)
    elif protection_policy == "source-text-survey":
        if version is None:
            raise ValueError("Font survey requires the supported original version")
        from .font_usage import collect_protected_codes
        protected, _usage_report = collect_protected_codes(image.path, version)
    elif protection_policy == "poc-source-text":
        protected = retained_codes(image, elf_recipe)
    else:
        raise ValueError(f"Unknown font protection policy: {protection_policy}")
    code_range = config["font_allowed_codes"]
    allowed = range(code_range["first"], code_range["last"] + 1)
    font_texts = [row["target"] for row in entries] + list((name_targets or {}).values())
    font_texts += [row["target"] for row in (plaintext_replacements or {}).values()]
    font_texts += list(additional_font_texts)
    font = build_font(fnt, textures, font_texts, font_path,
                      font_spec["sha256"], pixel_size=config["font_pixel_size"],
                      forbidden_codes=protected, allowed_codes=allowed,
                      raster_policy=config.get("font_raster"))
    encode = lambda text: encode_text(text, font.mapping)
    for row in entries:
        if decode_text(encode(row["target"]), font.mapping) != row["target"]:
            raise ValueError(f"Encoding round trip failed: {row['id']}")
    replacement = {"RES/SYSTEM.RES": original_font.replace(font.textures)}
    grouped = defaultdict(list)
    for row in entries:
        grouped[row["resource"]].append(row)
    for resource_name, rows in grouped.items():
        original = image.read(resource_name)
        kinds = {row["kind"] for row in rows}
        if kinds == {"elf"}:
            recipe_by_id = {row["id"]: row for row in elf_recipe["entries"]}
            if resource_name != elf_recipe["resource"]:
                raise ValueError("ELF recipe/resource mismatch")
            for row in rows:
                recipe = recipe_by_id.get(row["id"])
                if recipe is None or any(row[k] != recipe[k] for k in ("offset", "capacity", "source")):
                    raise ValueError(f"ELF recipe mismatch: {row['id']}")
            replacement[resource_name] = patch_executable(original, rows, encode)
        elif kinds == {"script"}:
            archive = parse_res(original)
            member_rows = defaultdict(list)
            for row in rows:
                member_rows[row["member"]].append(row)
            member_payloads = {}
            for member, selected in member_rows.items():
                script = archive.read(member)
                records = extract_strings(script, member)
                by_id = {r.id: r for r in records}
                for row in selected:
                    record = by_id.get(row["script_id"])
                    if record is None or (record.source, record.offset, record.capacity, record.source_sha256) != (
                            row["source"], row["offset"], row["capacity"], row["source_sha256"]):
                        raise ValueError(f"Script source mismatch: {row['id']}")
                member_payloads[member] = patch_strings(
                    script, records, {r["script_id"]: r["target"] for r in selected}, encode=encode,
                    literal_translations={r["script_id"]: r["literal_token_translations"] for r in selected
                                          if r.get("literal_token_translations")})
            replacement[resource_name] = archive.replace(member_payloads)
        else:
            raise ValueError(f"Mixed resource edit types: {resource_name}")
    for name, payload in replacement.items():
        if len(payload) != image.get(name).size:
            raise ValueError(f"Resource changed size: {name}")
    return replacement, font, sorted(protected)
