"""Import a reviewed native-size RGB PNG as a reversible source-bound delta."""
import argparse
import json
from pathlib import Path
from PIL import Image
from _bootstrap import ROOT
from mysticnights.artwork import digest
from mysticnights.raw_images import make_raw_delta, apply_raw_delta


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--source-sha256",required=True)
    parser.add_argument("--png",type=Path,required=True)
    parser.add_argument("--recipe",type=Path,required=True,help="JSON: profile, allowed_rectangles, targets")
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    source=args.source.read_bytes()
    if digest(source)!=args.source_sha256:raise ValueError("Raw artwork import source identity mismatch")
    recipe=json.loads(args.recipe.read_text("utf8"))
    with Image.open(args.png) as png:
        if png.mode!="RGB" or list(png.size)!=recipe["profile"][:2]:
            raise ValueError("Raw artwork import requires native-size RGB PNG")
        modified=png.tobytes()
    patch=make_raw_delta(source,modified,recipe["profile"],recipe["allowed_rectangles"],recipe["targets"])
    with args.output.open("x",encoding="utf8",newline="\n") as output:
        output.write(json.dumps(patch,ensure_ascii=False,separators=(",",":"))+"\n")
    reopened=json.loads(args.output.read_text("utf8"))
    if apply_raw_delta(source,reopened)!=modified or apply_raw_delta(modified,reopened,reverse=True)!=source:
        raise ValueError("Raw artwork import readback failed")
    print(f"RAW ARTWORK IMPORT PASS ranges={len(patch['ranges'])} sha256={patch['modified_sha256']}")


if __name__=="__main__":main()
