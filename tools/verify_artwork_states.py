"""Read authored paired-state checks back from a built ISO; never runs the game."""
import argparse
import json
from pathlib import Path
from _bootstrap import ROOT
from mysticnights.artwork import digest, load_graphics_catalogue
from mysticnights.artwork_checks import check_state_pairs, check_clear_regions, check_size_groups, check_shape_pairs
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
        if not any(k in patch for k in ('state_checks','clear_regions','size_groups','shape_pairs')):continue
        for ref in textures[patch["source_sha256"]]["references"]:
            data=parse_res(image.read(ref["resource"])).read(ref["member"])
            if digest(data)!=patch["modified_sha256"]:
                raise ValueError("Installed artwork differs from catalogue: "+ref["member"])
            decoded,_=decode_tim2(data)
            rows=check_state_pairs(decoded,patch.get("state_checks",[]))
            clear=check_clear_regions(decoded,patch.get("clear_regions",[]))
            sizes=check_size_groups(decoded,patch.get('size_groups',[]))
            shapes=check_shape_pairs(decoded,patch.get('shape_pairs',[]))
            if not rows and not clear and not sizes and not shapes:raise ValueError("Empty installed artwork checks")
            report.append({"resource":ref["resource"],"member":ref["member"],
                           "sha256":digest(data),"pairs":rows,"clear_regions":clear,"size_groups":sizes,"shape_pairs":shapes})
    if not report:raise ValueError("Catalogue declares no artwork state checks")
    print(json.dumps(report,ensure_ascii=False,indent=2))
    print(f"ARTWORK STATES PASS members={len(report)} pairs={sum(len(r['pairs']) for r in report)} installed=identical")
    print(f"ARTWORK GUTTERS PASS regions={sum(len(r['clear_regions']) for r in report)} nontransparent_pixels=0")
    print(f"ARTWORK PEER SIZES PASS groups={sum(len(r['size_groups']) for r in report)}")
    shape_count=sum(len(r['shape_pairs']) for r in report)
    if shape_count:
        print(f"ARTWORK SHAPES/CENTERS PASS pairs={shape_count} silhouettes=identical max_center_error=0.5px")
    else:
        print('ARTWORK SHAPES/CENTERS NOT_DECLARED pairs=0; no silhouette/center proof claimed')


if __name__=="__main__":main()
