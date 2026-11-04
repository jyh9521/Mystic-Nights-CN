"""Convert reviewed, native-size artist PNG pixels into a reversible TIM2 delta."""
import argparse
import json
from pathlib import Path
from PIL import Image
from _bootstrap import ROOT
from mysticnights.artwork import import_indexed_pixels, make_artwork_delta, apply_artwork


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--png", type=Path, required=True)
    parser.add_argument("--recipe", type=Path, required=True, help="JSON with allowed_rectangles and targets")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.read_bytes()
    recipe = json.loads(args.recipe.read_text("utf8"))
    with Image.open(args.png) as png:
        modified = import_indexed_pixels(source, png.convert("RGBA"), recipe["allowed_rectangles"],
                                         source_sha256=args.source_sha256)
    patch = make_artwork_delta(source, modified, recipe["allowed_rectangles"], recipe["targets"])
    if "state_checks" in recipe:
        patch["state_checks"] = recipe["state_checks"]
        apply_artwork(source, patch)  # Reject failed visual checks before publishing the delta.
    serialized = json.dumps(patch, ensure_ascii=False, separators=(",", ":")) + "\n"
    with args.output.open("x", encoding="utf8", newline="\n") as output:
        output.write(serialized)
    reopened = json.loads(args.output.read_text("utf8"))
    if apply_artwork(source, reopened) != modified or apply_artwork(modified, reopened, reverse=True) != source:
        raise ValueError("Artwork import readback failed")
    print(f"ARTWORK IMPORT PASS ranges={len(patch['ranges'])} sha256={patch['modified_sha256']}")


if __name__ == "__main__":
    main()
