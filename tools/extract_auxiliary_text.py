"""Inventory additional text paths; discovery does not authorize binary edits."""
import argparse
import hashlib
import json
from pathlib import Path

from _bootstrap import ROOT
from mysticnights.versions import load_version, verify_original
from inspect_links import write_reports


from mysticnights.auxiliary import nul_candidates, extract_auxiliary


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
