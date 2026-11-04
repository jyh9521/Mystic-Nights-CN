"""Reproducible editable catalogues; untranslated and protected data stay explicit."""
from collections import Counter
import hashlib
import json
from pathlib import Path

from .resources import parse_res
from .scripts import extract_strings


def prepare_catalogues(image, recipe: dict, locale: str) -> dict:
    groups = {name: [] for name in ("dialogue", "items", "documents", "interface", "other")}
    document_sources = {}
    for name in sorted(image.files):
        if not name.endswith(".RES"):
            continue
        archive = parse_res(image.read(name))
        for member in archive.entries:
            if not member.name.endswith(".SCR"):
                continue
            payload = archive.read(member)
            if member.name == "DOCUMENT.SCR":
                document_sources[name] = payload
                if name == "RES/UI/DOCUMENT.RES":
                    continue
            for record in extract_strings(payload, member.name):
                if record.role != "display":
                    continue
                group = {"EVENT.SCR": "dialogue", "ITEM.SCR": "items", "DOCUMENT.SCR": "documents"}.get(member.name, "other")
                text_type = "dialogue" if group == "dialogue" else "document" if group == "documents" else "item_description" if record.command == "DESCRIPTION" else "system_message"
                row = {"id": f"{name}:{record.id}", "resource": name, "member": member.name,
                       "kind": "script", "script_id": record.id, "offset": record.offset,
                       "capacity": record.capacity, "source": record.source,
                       "source_sha256": record.source_sha256, "command": record.command,
                       "context": record.context, "line": record.line, "role": record.role,
                       "text_type": text_type, "target": "", "status": "untranslated"}
                if not record.source.strip():
                    row.update(status="non_text", target=record.source)
                if group == "documents":
                    row["mirrored_resources"] = ["RES/UI/DOCUMENT.RES"]
                groups[group].append(row)
    if set(document_sources) != {"RES/UI/ITEM.RES", "RES/UI/DOCUMENT.RES"} or len(set(document_sources.values())) != 1:
        raise ValueError("Expected exactly two byte-identical document scripts")
    executable = image.read(recipe["resource"])
    for item in recipe["entries"]:
        expected = item["source"].encode("cp949") + b"\0"
        if executable[item["offset"]:item["offset"] + item["capacity"]] != expected:
            raise ValueError(f"ELF source mismatch: {item['id']}")
        groups["interface"].append({**item, "kind": "elf", "resource": recipe["resource"],
                                     "source_sha256": hashlib.sha256(expected).hexdigest(),
                                     "role": item.get("role", "display"), "text_type": "system_message",
                                     "target": "", "status": "untranslated"})
    reports = {f"{name}.json": {"locale": locale, "entries": rows} for name, rows in groups.items() if rows}
    reports["catalogue.json"] = {"format": "localization-catalogue", "version": 1,
                                "locale": locale, "profile": "partial", "files": list(reports)}
    return reports


def read_project(path: Path) -> dict:
    """Read one-level source files, validate all IDs, then select explicit drafts.

    Empty translations are never silently interpreted as removals. Mirrored
    documents are expanded from a single target; build-time source checks still
    apply to every physical destination.
    """
    index = json.loads(path.read_text(encoding="utf-8"))
    if (index.get("format"), index.get("version"), index.get("profile")) != ("localization-catalogue", 1, "partial"):
        raise ValueError("Unsupported translation project")
    files = index.get("files")
    if not isinstance(files, list) or not files or len(set(files)) != len(files):
        raise ValueError("Invalid or duplicate catalogue files")
    entries, states, seen, hashes = [], Counter(), set(), {}
    for filename in files:
        relative = Path(filename)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Catalogue path escapes project")
        source = (path.parent / relative).resolve()
        if not source.is_relative_to(path.parent.resolve()) or source == path.resolve():
            raise ValueError("Catalogue path escapes project or references itself")
        raw = source.read_bytes()
        hashes[filename] = hashlib.sha256(raw).hexdigest()
        data = json.loads(raw)
        if data.get("locale") != index["locale"] or not isinstance(data.get("entries"), list):
            raise ValueError(f"Catalogue locale/entries mismatch: {filename}")
        for row in data["entries"]:
            if row["id"] in seen:
                raise ValueError(f"Duplicate project ID: {row['id']}")
            seen.add(row["id"])
            status, target = row.get("status"), row.get("target")
            if status not in {"untranslated", "non_text", "draft", "reviewed"}:
                raise ValueError(f"Invalid translation status: {row['id']}")
            if not isinstance(row.get("source"), str) or not isinstance(target, str):
                raise ValueError(f"Invalid text values: {row['id']}")
            if status == "untranslated" and target != "":
                raise ValueError(f"Untranslated entry has target text: {row['id']}")
            if status == "non_text" and (row["source"].strip() or target != row["source"]):
                raise ValueError(f"Only source whitespace can be non-text: {row['id']}")
            states[status] += 1
            if status not in {"draft", "reviewed"}:
                continue
            if not target.strip():
                raise ValueError(f"Missing translation: {row['id']}")
            base = {k: v for k, v in row.items() if k != "mirrored_resources"}
            entries.append(base)
            mirrors = row.get("mirrored_resources", [])
            if row.get("member") == "DOCUMENT.SCR" and mirrors != ["RES/UI/DOCUMENT.RES"]:
                raise ValueError(f"Missing required document mirror: {row['id']}")
            if mirrors and (row["kind"] != "script" or row["member"] != "DOCUMENT.SCR"
                            or row["resource"] != "RES/UI/ITEM.RES" or mirrors != ["RES/UI/DOCUMENT.RES"]):
                raise ValueError(f"Unverified mirror relation: {row['id']}")
            for resource in mirrors:
                entries.append({**base, "resource": resource, "id": f"{resource}:{row['script_id']}"})
    return {"locale": index["locale"], "profile": "partial", "entries": entries,
            "coverage": {"logical_catalogue_fields": len(seen), "states": dict(states),
                         "selected_physical_fields": len(entries)}, "catalogue_files_sha256": hashes}
