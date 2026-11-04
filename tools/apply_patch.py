"""Apply or reverse a verified sparse patch into a new disc-image copy."""
import argparse
import json
from pathlib import Path

from _bootstrap import ROOT
from mysticnights.patch import apply_patch


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--patch", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--reverse", action="store_true")
    args = parser.parse_args()
    result = apply_patch(args.input, args.patch, args.output, reverse=args.reverse)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
