"""Read authored paired-state checks back from a built ISO; never runs the game."""
import argparse
import json
from pathlib import Path
from _bootstrap import ROOT
from mysticnights.artwork import digest, load_graphics_catalogue
from mysticnights.artwork_checks import check_state_pairs
from mysticnights.graphics import decode_tim2
from mysticnights.iso9660 import IsoImage
from mysticnights.resources import parse_res


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iso",type=Path,required=True)
    parser.add_argument("--catalogue",type=Path,required=True)
    parser.add_argument("--slots",type=Path,default=ROOT/"assets/graphics-text-slots.json")
    args=parser.parse_args()
    catalogue=load_graphics_catalogue(args.catalogue)
    textures={t["sha256"]:t for t in json.loads(args.slots.read_text("utf8"))["textures"]}
    image=IsoImage(args.iso);report=[]
    for patch in catalogue["artwork_patches"]:
        if "state_checks" not in patch:continue
        for ref in textures[patch["source_sha256"]]["references"]:
            data=parse_res(image.read(ref["resource"])).read(ref["member"])
            if digest(data)!=patch["modified_sha256"]:
                raise ValueError("Installed artwork differs from catalogue: "+ref["member"])
            decoded,_=decode_tim2(data)
            rows=check_state_pairs(decoded,patch["state_checks"])
            if not rows:raise ValueError("Empty installed artwork state checks")
            report.append({"resource":ref["resource"],"member":ref["member"],
                           "sha256":digest(data),"pairs":rows})
    if not report:raise ValueError("Catalogue declares no artwork state checks")
    print(json.dumps(report,ensure_ascii=False,indent=2))
    print(f"ARTWORK STATES PASS members={len(report)} pairs={sum(len(r['pairs']) for r in report)} installed=identical")


if __name__=="__main__":main()
