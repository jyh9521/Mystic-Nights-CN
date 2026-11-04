"""Extract editable full-text templates into a new directory, without auto-translation."""
import argparse
import json
from pathlib import Path

from _bootstrap import ROOT
from mysticnights.catalogues import prepare_catalogues
from mysticnights.versions import load_version, verify_original
from inspect_links import write_reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iso", required=True, type=Path)
    parser.add_argument("--locale", default="zh-CN")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    image = verify_original(args.iso, load_version(ROOT / "assets/game-version.json"))
    recipe = json.loads((ROOT / "assets/elf-text-slots.json").read_text(encoding="utf-8"))
    reports = prepare_catalogues(image, recipe, args.locale)
    write_reports(reports, args.output)
    counts = {name: len(data["entries"]) for name, data in reports.items() if "entries" in data}
    print("CATALOGUES " + json.dumps(counts, sort_keys=True))
    print("MIRRORS documents=2 single_source=true")


if __name__ == "__main__":
    main()
