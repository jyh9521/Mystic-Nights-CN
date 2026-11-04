"""Read-only CLI for the version-locked retained-text font-slot survey."""
import argparse
import json
import os
from pathlib import Path

from _bootstrap import ROOT
from mysticnights.font_usage import collect_protected_codes
from mysticnights.versions import load_version


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iso", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="new JSON path")
    parser.add_argument("--skip-opaque-audit", action="store_true", help="omit diagnostic binary scans; protected set is unchanged")
    args = parser.parse_args()
    try:
        if os.path.lexists(args.output) or args.output.resolve() == args.iso.resolve():
            raise FileExistsError(f"Output must be new and distinct from original: {args.output}")
        version = load_version(ROOT / "assets/game-version.json")
        protected, report = collect_protected_codes(args.iso, version, audit_unknown=not args.skip_opaque_audit)
        serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(serialized)
        if json.loads(args.output.read_text(encoding="utf-8")) != report:
            raise ValueError("Font usage JSON readback mismatch")
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"FONT_USAGE_ERROR: {exc}\n")
    print(f"FONT_USAGE scr={report['counts']['scr_members']} plaintext_codes={report['counts']['plaintext_used_codes']} "
          f"protected={len(protected)} candidates={len(report['protection']['candidate_codes'])} "
          f"raw_main_limit={report['diagnostic_extremes']['plaintext_plus_any_main_load_byte_pair_candidate_count']} "
          f"globally_proved_idle=false")


if __name__ == "__main__":
    main()
