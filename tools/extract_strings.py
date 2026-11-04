"""Extract structured text candidates from a verified original disc.

The report separates display fields, shared display/logic identifiers and
protected references. Discovery never authorizes a field to be patched.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import tempfile

from _bootstrap import ROOT
from mysticnights.resources import parse_res
from mysticnights.scripts import extract_strings
from mysticnights.versions import load_version, verify_original


def _extract(image, output: Path) -> dict:
    catalogue, archives = [], []
    for name in sorted(image.files):
        if not name.endswith(".RES"):
            continue
        data = image.read(name)
        resource = parse_res(data)
        archives.append({"path": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                         "members": [{"name": m.name, "group": m.group, "offset": m.offset,
                                      "size": m.size} for m in resource.entries]})
        for member in resource.entries:
            if not member.name.endswith(".SCR"):
                continue
            for row in extract_strings(resource.read(member), member.name):
                entry = row.as_dict()
                entry.update({"id": f"{name}:{row.id}", "resource": name, "target": "",
                              "status": "untranslated" if row.role.startswith("display") else "protected"})
                catalogue.append(entry)
    recipe = json.loads((ROOT / "assets/elf-text-slots.json").read_text(encoding="utf-8"))
    executable = image.read(recipe["resource"])
    for row in recipe["entries"]:
        expected = row["source"].encode("cp949") + b"\0"
        if executable[row["offset"]:row["offset"] + row["capacity"]] != expected:
            raise ValueError(f"ELF original bytes mismatch: {row['id']}")
        catalogue.append({**row, "resource": recipe["resource"], "role": row.get("role", "display"),
                          "target": "", "status": "untranslated"})
    summary = {"iso_files": len(image.files), "res_files": len(archives), "quoted_and_elf_fields": len(catalogue),
               "roles": dict(sorted(Counter(row["role"] for row in catalogue).items())),
               "note": "Counts are extracted fields, not a percentage of all player-visible game text."}
    for filename, data in (("catalogue.json", catalogue), ("resources.json", archives), ("summary.json", summary)):
        (output / filename).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def extract(image, output: Path) -> dict:
    if output.exists():
        raise FileExistsError(f"Use a new output directory: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    parent = output.parent.resolve()
    with tempfile.TemporaryDirectory(prefix=f".{output.name}-", dir=parent) as temporary:
        work = Path(temporary).resolve()
        if work.parent != parent or output.resolve().parent != parent:
            raise ValueError("Extraction output escaped its intended parent")
        summary = _extract(image, work)
        for name in ("catalogue.json", "resources.json", "summary.json"):
            json.loads((work / name).read_text(encoding="utf-8"))
        if output.exists():
            raise FileExistsError(f"Output appeared during extraction: {output}")
        work.rename(output)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iso", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    version = load_version(ROOT / "assets/game-version.json")
    image = verify_original(args.iso, version)
    print(json.dumps(extract(image, args.output), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
