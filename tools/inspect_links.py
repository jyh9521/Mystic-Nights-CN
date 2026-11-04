"""Catalogue item/document links from a verified original ISO without editing it.

An optional extracted English-reference tree adds same-slot item names and
whole-document reference pages.  Missing reference files are permitted.  The
reported minimum capacities cover RES references only, never ELF mirrors.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Iterable, Mapping

from _bootstrap import ROOT
from mysticnights.resources import ResArchive, parse_res
from mysticnights.scripts import ScriptString, extract_strings, patch_strings
from mysticnights.versions import load_version, verify_original


CAPACITY_SCOPE = (
    "RES quoted fields and recognized SCN item-name spans only; "
    "ELF mirrors are not included. These are discovery records, not patch authorization."
)
PAGE_NOTE = (
    "English documents can add or merge pages. References are paired by the "
    "canonical item NAME, not by page number or absolute text offset."
)


def scan_scene_keys(payload: bytes) -> list[dict]:
    """Recognize complete bounded type-0x0068 item keys, never substrings.

    The known pattern is u16 0x0068, name[32], model filename[32].  Original
    bytes after the first name NUL can contain nonzero stale data.  Consequently
    capacity is only the pre-NUL byte count, not the entire 32-byte field.
    This is a finite recognized pattern, not a parser for the complete SCN.
    """
    found = []
    for match in re.finditer(rb"h\x00", payload):
        offset = match.end()
        if offset + 64 > len(payload):
            continue
        name_field = payload[offset : offset + 32]
        model_field = payload[offset + 32 : offset + 64]
        if b"\0" not in name_field or b"\0" not in model_field:
            continue
        name = name_field.split(b"\0", 1)[0]
        model = model_field.split(b"\0", 1)[0]
        if not name or re.fullmatch(rb"[A-Za-z0-9_.-]+\.GEO", model) is None:
            continue
        try:
            decoded = name.decode("cp949")
        except UnicodeDecodeError:
            continue
        if any(ord(char) < 32 for char in decoded):
            continue
        found.append({
            "source_ko": decoded,
            "member_relative_offset": offset,
            "capacity": len(name),
            "field_bytes": 32,
            "prefix_hex": "6800",
            "model": model.decode("ascii"),
            "source_sha256": hashlib.sha256(name).hexdigest(),
            "field_sha256": hashlib.sha256(name_field).hexdigest(),
            "classification": "recognized type-0x0068/name[32]/GEO[32] pattern",
        })
    return found


def _record_dict(record: ScriptString, payload: bytes) -> dict:
    row = record.as_dict()
    if record.command == "TEXT":
        start = payload.rfind(b"\n", 0, record.offset) + 1
        prefix = payload[start : record.offset]
        match = re.match(rb"\s*TEXT\s+(\d+)\s", prefix)
        row["page_number"] = int(match[1]) if match else None
    return row


def _document_blocks(payload: bytes | None) -> dict[str, list[dict]]:
    if payload is None:
        return {}
    if payload.splitlines()[0].strip() != b"SCR_TYPE DOC":
        raise ValueError("Document reference is not SCR_TYPE DOC")
    blocks = defaultdict(list)
    for record in extract_strings(payload, "DOCUMENT.SCR"):
        if record.command in {"NAME", "TEXT"}:
            blocks[record.context].append(_record_dict(record, payload))
    result = dict(blocks)
    for context, fields in result.items():
        if sum(field["command"] == "NAME" for field in fields) != 1:
            raise ValueError(f"Expected exactly one document NAME in {context}")
    return result


def pair_document_blocks(
    original: bytes,
    english: bytes | None,
    item_name_references: Mapping[str, str | None],
) -> dict:
    """Pair whole ITEM blocks by canonical names; do not imply page equivalence."""
    original_blocks = _document_blocks(original)
    english_blocks = _document_blocks(english)
    by_name: dict[str, tuple[str, list[dict]]] = {}
    for context, fields in english_blocks.items():
        name = next(field["source_ko"] for field in fields if field["command"] == "NAME").rstrip(" ")
        if name in by_name:
            raise ValueError(f"Ambiguous English document name: {name!r}")
        by_name[name] = context, fields
    used: set[str] = set()
    output = {}
    for context, fields in original_blocks.items():
        source_name = next(field["source_ko"] for field in fields if field["command"] == "NAME")
        reference_name = item_name_references.get(source_name)
        reference_key = reference_name.rstrip(" ") if reference_name is not None else None
        paired = by_name.get(reference_key) if reference_key is not None else None
        if paired is not None:
            if paired[0] in used:
                raise ValueError(f"English document block matched more than once: {reference_key!r}")
            used.add(paired[0])
        output[context] = {
            "source_name": source_name,
            "reference_name": reference_name,
            "reference_alignment": "canonical item NAME mapping" if paired else "unavailable or unmatched",
            "ko": fields,
            "en": paired[1] if paired else [],
        }
    return {
        "note": PAGE_NOTE,
        "blocks": output,
        "unmatched_en_blocks": {key: value for key, value in english_blocks.items() if key not in used},
    }


def _reference_archive(root: Path | None, resource: str) -> tuple[ResArchive | None, dict | None]:
    if root is None:
        return None, None
    relative = PurePosixPath(resource)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ValueError(f"Invalid reference resource path: {resource}")
    path = root.joinpath(*relative.parts).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Reference path escapes its selected root: {resource}")
    if not path.exists():
        return None, None
    data = path.read_bytes()
    return parse_res(data), {"path": resource, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _reference_member(archive: ResArchive | None, name: str, group: int) -> bytes | None:
    if archive is None:
        return None
    matches = [entry for entry in archive.entries if entry.name == name and entry.group == group]
    if len(matches) > 1:
        raise ValueError(f"Ambiguous reference member: group={group}, name={name}")
    return archive.read(matches[0]) if matches else None


def link_item_names(catalogue: Iterable[dict], scene_keys: Iterable[dict]) -> list[dict]:
    """Attach only whole-field names to the canonical SUBSYS item table."""
    catalogue, scene_keys = list(catalogue), list(scene_keys)
    canonical = [row for row in catalogue if row["resource"] == "RES/SUBSYS.RES"
                 and row["member"] == "ITEM.SCR" and row["command"] == "NAME"]
    source_names = [row["source_ko"] for row in canonical]
    source_ids = [row["context"] for row in canonical]
    if len(set(source_names)) != len(source_names) or len(set(source_ids)) != len(source_ids):
        raise ValueError("Canonical item IDs and NAME values must each be unique")
    quoted_by_name = defaultdict(list)
    for row in catalogue:
        if row["role"] not in {"display_identifier", "item_reference"}:
            continue
        quoted_by_name[row["source_ko"]].append({
            "kind": "quoted", "resource": row["resource"], "member": row["member"],
            "id": row["id"], "offset": row["absolute_offset"], "capacity": row["capacity"],
            "command": row["command"], "source_sha256": row["source_sha256"],
        })
    scene_by_name = defaultdict(list)
    for row in scene_keys:
        scene_by_name[row["source_ko"]].append({"kind": "scene-item-name", **row})
    result = []
    for item in canonical:
        source = item["source_ko"]
        references = quoted_by_name[source] + scene_by_name[source]
        if not references:
            raise ValueError(f"Canonical item has no source reference: {source!r}")
        result.append({
            "id": item["context"], "source_ko": source,
            "reference_en": item["reference_en"],
            "minimum_capacity": min(row["capacity"] for row in references),
            "capacity_scope": CAPACITY_SCOPE,
            "references": references,
        })
    return result


def inspect(image, upstream: Path | None = None) -> dict[str, object]:
    """Return serializable reports from an ISO reader (no extraction tree needed)."""
    if upstream is not None:
        upstream = upstream.resolve()
        if not upstream.is_dir():
            raise ValueError(f"Upstream reference root is not a directory: {upstream}")
    inventories, catalogue, scene_keys, upstream_files = [], [], [], []
    documents: dict[str, tuple[bytes, bytes | None]] = {}
    script_members = 0
    for name in sorted(image.files):
        if not name.endswith(".RES"):
            continue
        data = image.read(name)
        resource = parse_res(data)
        reference, identity = _reference_archive(upstream, name)
        if identity:
            upstream_files.append(identity)
        inventories.append({"path": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                            "groups": resource.group_counts, "members": [vars(entry) for entry in resource.entries]})
        for member in resource.entries:
            if member.name.endswith(".SCN"):
                for row in scan_scene_keys(resource.read(member)):
                    scene_keys.append({**row, "resource": name, "member": member.name,
                                       "offset": member.offset + row["member_relative_offset"]})
            if not member.name.endswith(".SCR"):
                continue
            script_members += 1
            payload = resource.read(member)
            fields = extract_strings(payload, member.name)
            round_trip = patch_strings(payload, fields, {row.id: row.source for row in fields if row.role == "display"})
            if round_trip != payload:
                raise ValueError(f"Original script no-op round trip differed: {name}/{member.name}")
            en_payload = _reference_member(reference, member.name, member.group)
            en_fields = extract_strings(en_payload, member.name) if en_payload is not None else []
            en_by_id = {row.id: row for row in en_fields}
            if member.name == "DOCUMENT.SCR":
                documents[name] = payload, en_payload
            for field in fields:
                row = _record_dict(field, payload)
                row.update({"id": f"{name}:{field.id}", "resource": name,
                            "member_offset": member.offset, "absolute_offset": member.offset + field.offset,
                            "reference_en": None, "reference_alignment": None})
                en_field = en_by_id.get(field.id)
                if (member.name != "DOCUMENT.SCR" and en_field is not None
                        and en_field.command == field.command and en_field.capacity == field.capacity):
                    row.update({"reference_en": en_field.source, "reference_alignment": "same byte slot"})
                catalogue.append(row)
    item_names = link_item_names(catalogue, scene_keys)
    known_names = {row["source_ko"] for row in item_names}
    for row in scene_keys:
        row["canonical_item_found"] = row["source_ko"] in known_names
    name_map = {row["source_ko"]: row["reference_en"] for row in item_names}
    bundles = {name: pair_document_blocks(original, english, name_map)
               for name, (original, english) in documents.items()}
    summary = {
        "res_files": len(inventories), "script_members": script_members, "quoted_fields": len(catalogue),
        "roles": dict(sorted(Counter(row["role"] for row in catalogue).items())),
        "canonical_item_names": len(item_names), "scene_keys": len(scene_keys),
        "mapped_scene_keys": sum(row["canonical_item_found"] for row in scene_keys),
        "unmapped_scene_keys": sum(not row["canonical_item_found"] for row in scene_keys),
        "document_resources": len(bundles),
        "document_blocks": sum(len(bundle["blocks"]) for bundle in bundles.values()),
        "paired_document_blocks": sum(bool(block["en"]) for bundle in bundles.values() for block in bundle["blocks"].values()),
        "upstream_supplied": upstream is not None, "upstream_res_files": len(upstream_files),
        "round_trip": "All extracted original display fields reinserted byte-identically.",
        "capacity_scope": CAPACITY_SCOPE, "page_note": PAGE_NOTE,
        "runtime_status": "No game execution; counts do not establish complete player-visible text coverage.",
    }
    return {"resources.json": inventories, "strings.json": catalogue, "item_names.json": item_names,
            "scene_keys.json": scene_keys, "document_bundles.json": bundles,
            "upstream_files.json": upstream_files, "summary.json": summary}


def write_reports(reports: Mapping[str, object], output: Path) -> None:
    """Write and reopen reports in a new directory; never replace existing work."""
    serialized = {name: json.dumps(data, ensure_ascii=False, indent=2) + "\n" for name, data in reports.items()}
    if any(Path(name).name != name or not name.endswith(".json") for name in serialized):
        raise ValueError("Report names must be simple JSON filenames")
    output.mkdir(parents=True, exist_ok=False)
    for name, text in serialized.items():
        destination = output / name
        with destination.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        if destination.read_text(encoding="utf-8") != text:
            raise OSError(f"Report readback failed: {destination}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iso", required=True, type=Path)
    parser.add_argument("--upstream", type=Path, help="Optional extracted reference root containing RES/")
    parser.add_argument("--output", required=True, type=Path, help="New report directory")
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError(f"Output must be a new directory: {args.output}")
    version = load_version(ROOT / "assets/game-version.json")
    image = verify_original(args.iso, version)
    reports = inspect(image, args.upstream)
    reports["summary.json"]["source_iso"] = version["iso"]
    write_reports(reports, args.output)
    print(json.dumps(reports["summary.json"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
