"""Build a defensive RES/SCN/main-ELF linked-name manifest; never rename items."""

import argparse
import json
from pathlib import Path

from _bootstrap import ROOT
from inspect_links import inspect, write_reports
from mysticnights.linked_names import MAIN_ELF, audit_elf_suffix_references, discover_name_links
from mysticnights.versions import load_version, verify_original


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iso", required=True, type=Path)
    parser.add_argument("--upstream", type=Path, help="Optional extracted English-reference tree")
    parser.add_argument("--output", required=True, type=Path, help="New output directory")
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError(f"Output must be a new directory: {args.output}")
    version = load_version(ROOT / "assets/game-version.json")
    image = verify_original(args.iso, version)
    previous_report = inspect(image, args.upstream)
    manifest = discover_name_links(image, inspect_report=previous_report)
    suffix_audit = audit_elf_suffix_references(image.read(MAIN_ELF), manifest["elf_rejected_suffixes"],
                                             [field for group in manifest["groups"] for field in group["references"] if field["kind"] == "elf"])
    manifest["source_iso"] = version["iso"]
    summary = {**manifest["summary"], "core_sha256": manifest["core_sha256"],
               "source_iso": version["iso"], "limitations": manifest["limitations"],
               "capacity_semantics": manifest["capacity_semantics"], "suffix_reference_audit": suffix_audit["summary"]}
    write_reports({"manifest.json": manifest, "summary.json": summary,
                   "network_names.json": manifest["network"],
                   "suffix-reference-audit.json": suffix_audit,
                   "minimum_capacities.json": [{"id": group["id"], "source": group["source"],
                                                "reference_en": group["reference_en"],
                                                "max_encoded_bytes": group["max_encoded_bytes"],
                                                "reference_count": len(group["references"])}
                                               for group in manifest["groups"]]}, args.output)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
