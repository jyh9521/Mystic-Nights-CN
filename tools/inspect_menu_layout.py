"""Recheck the original title-menu UV/scaling evidence without game execution."""
import argparse
import json
import re
from pathlib import Path
from _bootstrap import ROOT
from mysticnights.artwork import digest
from mysticnights.resources import parse_res
from mysticnights.versions import load_version, verify_original


def inspect(image):
    elf=image.read("SCKA_200.55")
    # Standard MIPS addiu argument loads in RenderLogo's unselected draw.
    # File position = VA - 0x100000 + 0x80 for this verified ELF's segment.
    words={0x137a8c:"80001324",0x137a90:"22011224",0x137ab0:"18007326",0x137ab8:"1c005226",
           0x137c1c:"17000224",0x137c28:"e2000524",0x137c30:"ba000724",
           0x137c34:"1e000824",0x137c38:"35000924",0x137c40:"7e000b24",
           0x137c44:"ac6f050c"}
    for va,expected in words.items():
        offset=va-0x100000+0x80
        if elf[offset:offset+4].hex()!=expected:
            raise ValueError(f"Menu renderer anchor mismatch at {va:#x}")
    raw=parse_res(image.read("RES/SYSTEM.RES")).read("UIDEF.SCR")
    text=raw.decode("cp949")
    names=["LOGO_NEW_GAME_ACTIVE","LOGO_LOAD_GAME_ACTIVE","LOGO_NETWORK_GAME_ACTIVE","LOGO_GALLERY_ACTIVE"]
    rows=[]
    for row,name in enumerate(names):
        pattern=(r'NAME\s+"'+name+r'"\s+POSITION\s+([\d\s]+?)\s+START_RENDER\s+TRUE\s+'
                 r'IMAGE_COUNT\s+1\s+IMAGE\s*\{\s*POSITION\s+([\d\s]+?)\s+UV\s+([\d\s]+?)\s+ANI_NUM')
        matches=re.findall(pattern,text)
        if len(matches)!=1:raise ValueError("Menu sprite definition mismatch: "+name)
        pos,rect,uv=[list(map(int,v.split())) for v in matches[0]]
        if pos!=[147,290+28*row] or rect!=[0,0,343,30] or uv!=[231,128+24*row,229,23]:
            raise ValueError("Unsupported menu sprite geometry")
        rows.append({"id":name,"position":pos,"destination":rect,"uv":uv})
    return {"elf_sha256":digest(elf),"uidef_sha256":digest(raw),
            "anchors":{hex(k):v for k,v in words.items()},
            "normal":{"position":[226,290],"destination":[186,30],"uv":[53,128,126,23],
                      "row_steps":{"screen":28,"uv":24}},
            "selected":rows,"normal_scale":[186/126,30/23],"selected_scale":[343/229,30/23],
            "selected_horizontal_scale_ratio":(343/229)/(186/126),
            "result":"MENU LAYOUT PASS vertical=equal horizontal_difference=1.46% steady_state_only"}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iso",required=True,type=Path)
    args=parser.parse_args()
    result=inspect(verify_original(args.iso,load_version(ROOT/"assets/game-version.json")))
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":main()
