"""Inventory additional text paths; discovery does not authorize binary edits."""
import argparse
import hashlib
import json
from pathlib import Path

from _bootstrap import ROOT
from mysticnights.versions import load_version, verify_original
from inspect_links import write_reports


def nul_candidates(data: bytes, encoding: str, unicode_ranges=()):
    offset = 0
    for raw in data.split(b"\0")[:-1]:
        try:
            source = raw.decode(encoding, errors="strict")
        except UnicodeDecodeError:
            source = ""
        printable = source and all(c.isprintable() or c in "\r\n\t" for c in source)
        selected = not unicode_ranges or any(low <= ord(c) <= high for c in source for low, high in unicode_ranges)
        if printable and selected:
            yield offset, raw, source
        offset += len(raw) + 1


def extract_auxiliary(image, recipe):
    reports = []
    for definition in recipe["sources"]:
        resource, encoding = definition["resource"], definition["encoding"]
        data = image.read(resource)
        layout = definition["layout"]
        if layout == "nul-candidates":
            values = list(nul_candidates(data, encoding, definition.get("unicode_ranges", [])))
        elif layout == "plain":
            values = [(0, data, data.decode(encoding, errors="strict"))]
        elif layout == "explicit-slots":
            values = []
            for slot in definition["slots"]:
                offset = slot["offset"]
                raw = slot["source"].encode(encoding)
                if data[offset:offset + len(raw) + 1] != raw + b"\0":
                    raise ValueError(f"Explicit auxiliary source mismatch: {resource}@{offset:x}")
                values.append((offset, raw, slot["source"]))
        else:
            raise ValueError(f"Unknown text source layout: {layout}")
        rows = [{"id": f"{resource}@{offset:08x}", "resource": resource, "offset": offset,
                 "source_bytes": len(raw), "source_sha256": hashlib.sha256(raw).hexdigest(),
                 "source": source, "target": "", "status": "untranslated", "encoding": encoding,
                 "role": "candidate_display", "patch_ready": False} for offset, raw, source in values]
        reports.append({"resource": resource, "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                        "encoding": encoding, "layout": layout, "separate_font": definition.get("font"),
                        "entries": rows})
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iso", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    version = load_version(ROOT / "assets/game-version.json")
    image = verify_original(args.iso, version)
    recipe = json.loads((ROOT / "assets/auxiliary-text-sources.json").read_text(encoding="utf8"))
    inventory = extract_auxiliary(image, recipe)
    summary = {r["resource"]: len(r["entries"]) for r in inventory}
    write_reports({"auxiliary.json": inventory, "summary.json": summary}, args.output)
    print("AUXILIARY " + json.dumps(summary, sort_keys=True))
    print("DISCOVERY_ONLY patch_ready=false")


if __name__ == "__main__":
    main()
