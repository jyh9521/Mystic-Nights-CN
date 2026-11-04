"""Validate editable catalogues without building or executing a game."""
import argparse
import csv
import json
from pathlib import Path

from _bootstrap import ROOT
from mysticnights.catalogues import prepare_catalogues, read_project
from mysticnights.executable import validate_tokens
from mysticnights.localization import load_catalogue
from mysticnights.scripts import protected_tokens
from mysticnights.typography import validate_text
from mysticnights.versions import load_version, verify_original


def validate_project(locale_dir: Path, image=None) -> dict:
    config = json.loads((locale_dir / "config.json").read_text(encoding="utf-8"))
    path = locale_dir / config["translations"]
    catalogue = load_catalogue(path)
    terms = json.loads((locale_dir / "terminology-checks.json").read_text(encoding="utf-8"))
    for row in catalogue["entries"]:
        target = row["target"]
        if any(c in target for c in ('\0', '\r', '\n', '"')):
            raise ValueError(f"Forbidden literal character: {row['id']}")
        validate_text(target, row["text_type"], config["punctuation"])
        validate_tokens(row["source"], target)
        if row["kind"] == "script" and protected_tokens(row["source"]) != protected_tokens(target):
            raise ValueError(f"Protected script tokens differ: {row['id']}")
        size = sum(1 if ord(c) < 128 else 2 for c in target) + (row["kind"] == "elf")
        if size > row["capacity"]:
            raise ValueError(f"Fixed-slot overflow {row['id']}: {size} > {row['capacity']}")
        for term in terms["rules"]:
            if term["source"] in row["source"] and not any(t in target for t in term["targets"]):
                raise ValueError(f"Terminology mismatch {row['id']}: {term['source']}")
    names = json.loads((locale_dir / "names.json").read_text(encoding="utf-8"))
    if names["locale"] != config["locale"]:
        raise ValueError("Name catalogue locale mismatch")
    identifiers, targets = set(), set()
    for row in names["entries"]:
        if row["id"] in identifiers or row["target"] in targets or not row["target"].strip():
            raise ValueError("Duplicate name ID, duplicate target, or empty item name")
        identifiers.add(row["id"]); targets.add(row["target"])
        if sum(1 if ord(c) < 128 else 2 for c in row["target"]) > row["minimum_res_capacity"]:
            raise ValueError(f"Name slot overflow: {row['id']}")
    with (locale_dir / "glossary.tsv").open(encoding="utf-8", newline="") as stream:
        glossary = list(csv.DictReader(stream, delimiter="\t"))
    by_id = {r["id"]: r for r in glossary}
    if len(by_id) != len(glossary):
        raise ValueError("Duplicate glossary ID")
    for row in names["entries"]:
        if row["id"] not in by_id or any(row[k] != by_id[row["id"]][k] for k in ("source", "target")):
            raise ValueError(f"Name/glossary inconsistency: {row['id']}")
    source_count = 0
    if image is not None:
        recipe = json.loads((ROOT / "assets/elf-text-slots.json").read_text(encoding="utf-8"))
        expected = prepare_catalogues(image, recipe, config["locale"])
        index = json.loads(path.read_text(encoding="utf-8"))
        if index["files"] != expected["catalogue.json"]["files"]:
            raise ValueError("Source catalogue file set changed")
        for filename in index["files"]:
            actual = json.loads((path.parent / filename).read_text(encoding="utf-8"))["entries"]
            source = expected[filename]["entries"]
            if len(actual) != len(source):
                raise ValueError(f"Source catalogue field count changed: {filename}")
            for before, after in zip(source, actual):
                for key, value in before.items():
                    if key not in {"target", "status", "role", "text_type"} and after.get(key) != value:
                        raise ValueError(f"Source metadata changed {before['id']}: {key}")
                if after["role"] != before["role"] and (before["role"], after["role"]) != ("candidate_display", "display"):
                    raise ValueError(f"Source role changed: {before['id']}")
                source_count += 1
        from mysticnights.linked_names import discover_name_links
        links = discover_name_links(image)
        originals = {r["id"]: r for r in links["groups"]}
        if set(originals) != identifiers:
            raise ValueError("Canonical item ID set changed")
        for row in names["entries"]:
            original = originals[row["id"]]
            if row["source"] != original["source"] or row["minimum_res_capacity"] != original["max_encoded_bytes"]:
                raise ValueError(f"Name source/capacity mismatch: {row['id']}")
    return {**catalogue["coverage"], "glossary_terms": len(glossary), "canonical_item_names": len(identifiers),
            "source_metadata_checked": source_count,
            "required_glyphs_with_names": len({c for r in catalogue["entries"] + names["entries"] for c in r["target"] if ord(c) >= 128})}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--locale", default="zh-CN")
    parser.add_argument("--iso", type=Path, help="Also re-extract and compare every original source field")
    args = parser.parse_args()
    if not args.locale or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for c in args.locale):
        parser.error("Invalid locale identifier")
    image = verify_original(args.iso, load_version(ROOT / "assets/game-version.json")) if args.iso else None
    print("TRANSLATIONS PASS " + json.dumps(validate_project(ROOT / "locales" / args.locale, image), sort_keys=True))


if __name__ == "__main__":
    main()
