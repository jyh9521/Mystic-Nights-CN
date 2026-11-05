"""Validate editable catalogues without building or executing a game."""
import argparse
import csv
import json
from pathlib import Path

from _bootstrap import ROOT
from mysticnights.catalogues import prepare_catalogues, read_project, validate_literal_fields
from mysticnights.executable import validate_tokens
from mysticnights.localization import load_catalogue
from mysticnights.scripts import validate_script_tokens
from mysticnights.typography import validate_text
from mysticnights.versions import load_version, verify_original


def validate_project(locale_dir: Path, image=None) -> dict:
    config = json.loads((locale_dir / "config.json").read_text(encoding="utf-8"))
    path = locale_dir / config["translations"]
    catalogue = load_catalogue(path)
    validate_literal_fields(catalogue["entries"], json.loads((ROOT / "assets/literal-text-fields.json").read_text(encoding="utf8")),
                            load_version(ROOT / "assets/game-version.json")["iso"]["sha256"])
    terms = json.loads((locale_dir / "terminology-checks.json").read_text(encoding="utf-8"))
    for row in catalogue["entries"]:
        target = row["target"]
        if any(c in target for c in ('\0', '\r', '\n', '"')):
            raise ValueError(f"Forbidden literal character: {row['id']}")
        typography = {**config["punctuation"],
                      "no_line_start": config.get("text_layout", {}).get("no_line_start", "")}
        validate_text(target, row["text_type"], typography)
        validate_tokens(row["source"], target)
        if row["kind"] == "script":
            validate_script_tokens(row["source"], target, row.get("literal_token_translations", []))
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
    auxiliary_counts = {}
    extra_targets = []
    graphics_coverage = {}
    raw_coverage = {}
    if catalogue["profile"] == "full-text":
        from mysticnights.auxiliary import read_auxiliary
        auxiliary = read_auxiliary(locale_dir, config, json.loads((ROOT / "assets/auxiliary-text-sources.json").read_text(encoding="utf8")), image)
        auxiliary_counts = {key: len(auxiliary[key]) for key in ("network", "agreement", "extra_interface")}
        extra_targets = auxiliary["agreement"] + auxiliary["extra_interface"]
        for row in catalogue["entries"] + names["entries"] + sum((auxiliary[key] for key in auxiliary_counts), []):
            if any(0xAC00 <= ord(c) <= 0xD7A3 or 0x3130 <= ord(c) <= 0x318F for c in row["target"]):
                raise ValueError(f"Untranslated Korean remains: {row['id']}")
        from mysticnights.save_metadata import build_save_metadata
        metadata = json.loads((locale_dir / config["save_metadata"]).read_text(encoding="utf8"))
        if metadata["locale"] != config["locale"]:
            raise ValueError("Save metadata locale mismatch")
        if image is not None:
            build_save_metadata(image, json.loads((ROOT / "assets/save-metadata-slots.json").read_text(encoding="utf8")), metadata)
        graphics_recipe = json.loads((ROOT / "assets/graphics-text-slots.json").read_text(encoding="utf8"))
        if config.get("graphics_review"):
            from mysticnights.graphics_review import validate_review
            review_path = (ROOT / config["graphics_review"]).resolve()
            if not review_path.is_relative_to(ROOT.resolve()):
                raise ValueError("Graphics review path escapes repository")
            validate_review(json.loads(review_path.read_text("utf8")), graphics_recipe, image)
        from mysticnights.artwork import load_graphics_catalogue
        graphics = load_graphics_catalogue(locale_dir / config["graphics"])
        slots = [slot for texture in graphics_recipe["textures"] for slot in texture["slots"]]
        graphic_ids = {r["id"] for r in graphics["entries"]}
        if (graphics.get("locale") != config["locale"] or len(graphic_ids) != len(graphics["entries"])
                or graphic_ids != {r["id"] for r in slots}
                or any(r.get("status") not in {"draft", "reviewed"} or not r.get("target", "").strip() for r in graphics["entries"])):
            raise ValueError("Graphics text catalogue is incomplete or mismatched")
        graphics_targets = {r["id"]: r["target"] for r in graphics["entries"]}
        authored = {t["sha256"]: t for t in graphics_recipe["textures"] if t.get("rendering") == "authored-delta"}
        patches = graphics.get("artwork_patches", [])
        if len(patches) != len(authored) or {r["source_sha256"] for r in patches} != set(authored):
            raise ValueError("Authored graphics coverage mismatch")
        for patch in patches:
            texture = authored[patch["source_sha256"]]
            if (patch["targets"] != {s["id"]: graphics_targets[s["id"]] for s in texture["slots"] if s["install"]}
                    or patch["allowed_rectangles"] != texture["artwork_rectangles"]):
                raise ValueError("Authored graphics text changed; redraw required")
        graphics_coverage = {"translated": len(graphic_ids), "selected_for_insertion": sum(bool(r.get("install")) for r in slots),
                             "retained_identifiers": sum(r.get("disposition") == "retain-identifier" for r in slots),
                             "pending_art_review": sum(not r.get("install") and r.get("disposition") != "retain-identifier" for r in slots)}
        if config.get("raw_images"):
            from mysticnights.raw_images import validate_raw_images, build_raw_images
            raw_recipe = json.loads((ROOT / "assets/raw-image-slots.json").read_text(encoding="utf8"))
            raw_catalogue = load_graphics_catalogue(locale_dir / config["raw_images"])
            if raw_catalogue["locale"] != config["locale"]:
                raise ValueError("Raw image locale mismatch")
            raw_coverage = validate_raw_images(raw_recipe, raw_catalogue)
            if image is not None:
                build_raw_images(image, raw_recipe, raw_catalogue)
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
            "auxiliary_translated_fields": auxiliary_counts,
            "graphics_text": graphics_coverage,
            "raw_images": raw_coverage,
            "source_metadata_checked": source_count,
            "required_main_glyphs": len({c for r in catalogue["entries"] + names["entries"] + extra_targets for c in r["target"] if ord(c) >= 128}),
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
