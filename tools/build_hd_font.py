#!/usr/bin/env python3
"""Build an optional, source-bound 4x main-font pack without launching PCSX2."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import tempfile

from _bootstrap import ROOT
from mysticnights.hd_font import (HdFontError, build_hd_atlases, render_hd_preview,
                                 tim2_replacement_identity, validate_inputs)
from mysticnights.iso9660 import IsoImage, sha256_file
from mysticnights.resources import parse_res


def _save_png(image, path: Path) -> dict:
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", compress_level=9)
    with Image.open(path) as reopened:
        reopened.load()
        if reopened.mode != "RGBA" or reopened.size != image.size or reopened.tobytes() != image.tobytes():
            raise HdFontError("PNG pixel readback disagrees")
    return {"sha256":sha256_file(path),"size":path.stat().st_size,
            "width":image.width,"height":image.height}


def _preview_entries(manifest: dict, mapping: dict) -> list[dict]:
    selected=[]
    # Source-bound real examples, not freshly invented review copy.
    for types in (("dialogue","cutscene"),("system_message",),("item_description",)):
        candidates=[e for e in manifest["entries"] if e.get("text_type") in types
                    and 5 <= len(e.get("target","")) <= 100
                    and not re.search(r"[<%\r\n]",e["target"])
                    and all(ord(c)<128 or c in mapping for c in e["target"])]
        if not candidates:
            raise HdFontError(f"no actual text available for preview types {types}")
        row=candidates[0]
        text=row["target"]
        # Only the proof image wraps; native target data and FNT remain untouched.
        wrapped="\n".join(text[i:i+36] for i in range(0,len(text),36))
        selected.append({"id":row["id"],"text_type":row["text_type"],"target":text,"preview_text":wrapped})
    # Include an actual mixed-script control/number sample when present. Old
    # Chinese-only previews concealed nearest-scaled Latin letters and digits.
    candidates=[e for e in manifest["entries"] if re.search(r"[A-Za-z][0-9]",e.get("target",""))
                and not re.search(r"[<%\r\n]",e["target"])
                and all(ord(c)<128 or c in mapping for c in e["target"])]
    if candidates and candidates[0]["id"] not in {e["id"] for e in selected}:
        row=candidates[0]; text=row["target"]
        selected.append({"id":row["id"],"text_type":row["text_type"],"target":text,
                         "preview_text":"\n".join(text[i:i+36] for i in range(0,len(text),36))})
    return selected


def build_pack(iso_path: Path, manifest_path: Path, font_path: Path, output: Path) -> dict:
    from PIL import Image, ImageDraw
    output=output.resolve()
    if output.exists():
        raise FileExistsError(f"output must be a new directory: {output}")
    manifest_bytes=manifest_path.read_bytes()
    manifest=json.loads(manifest_bytes)
    font_data=font_path.read_bytes()
    font_spec=json.loads((ROOT/"assets/font-source.json").read_text(encoding="utf8"))
    version=json.loads((ROOT/"assets/game-version.json").read_text(encoding="utf8"))
    serial=version["serial"]
    if not re.fullmatch(r"[A-Z]{4}-[0-9]{5}",serial):
        raise HdFontError("unsafe or unsupported game serial directory")
    image=IsoImage(iso_path)
    system=image.read("RES/SYSTEM.RES")
    validate_inputs(iso_path,manifest,font_data,font_spec,version,system,image.read("SYSTEM.CNF"))
    archive=parse_res(system)
    fnt=archive.read("FONT.FNT")
    textures={f"FONT_{i}.TM2":archive.read(f"FONT_{i}.TM2") for i in range(1,9)}
    font=manifest["font"]
    hd=build_hd_atlases(fnt,textures,font["mapping"],font_data,font["sha256"],
                       pixel_size=font["pixel_size"],native_raster_policy=font.get("raster_policy"),
                       ascii_outlines=True)
    examples=_preview_entries(manifest,font["mapping"])
    text="\n".join(e["preview_text"] for e in examples)
    native=render_hd_preview(fnt,textures,hd.images,text,font["mapping"],hd=False)
    high=render_hd_preview(fnt,textures,hd.images,text,font["mapping"],hd=True)
    nearest=native.resize((native.width*4,native.height*4),Image.Resampling.NEAREST)
    report={"format":"pcsx2-hd-main-font-pack","version":1,"pcsx2_source_revision":"v2.9.155",
            "serial":serial,"locale":manifest["locale"],"scale":4,
            "source_iso":manifest["modified"],
            "source_manifest_sha256":hashlib.sha256(manifest_bytes).hexdigest(),
            "source_fnt_sha256":hashlib.sha256(fnt).hexdigest(),
            "outline":{"name":font_spec["name"],"sha256":font["sha256"],
                       "pixel_size":font["pixel_size"],"hd_pixel_size":font["pixel_size"]*4},
            "mapped_glyphs":hd.mapped_glyphs,"common_baseline_shift_hd_pixels":hd.baseline_shift,
            "ascii_outline_glyphs":hd.ascii_glyphs,
            "ascii_layout":"fresh pinned outline, original native core-ink size/baseline and unchanged FNT metrics",
            "native_mapping_raster":"all mapped native cells independently re-rendered and matched",
            "unmapped_source_pixels":"protected runtime y+1/h-1 UV regions nearest-scaled and independently checked; unreferenced padding cleared",
            "sampling_padding":{"runtime_uv":"x,y+1,width,height-1 from existing FNT; integer FST endpoints",
                                "policy":"all texels outside every runtime glyph UV rectangle have zero alpha; no outline thresholding",
                                "cleared_source_pixels_native":hd.cleared_padding_pixels_native},
            "alpha_policy":"raw source CLUT peak RGB; outline coverage scales raw peak alpha; no doubled alpha in replacement PNG",
            "key_profile":{"texture":"XXH3-64(default seed), full native PSMT8 blocks in logical block-row order",
                           "palette":"XXH3-64(default seed), exact 256 logical raw RGBA CLUT entries",
                           "filename":"texturehash-palettehash-packedbits.png","wildcard_palette":False},
            "verified_offline":["exact source ISO / manifest / font / SYSTEM.RES identities",
                                "native mapping/raster correspondence and existing FNT layout",
                                "fresh mapped and ASCII outline glyphs, PNG roundtrip, untouched protected runtime UV regions",
                                "zero-alpha unreferenced font padding prevents stale source-ink bilinear leakage",
                                "hash algorithm and exact-CLUT lookup read from pinned PCSX2 primary source"],
            "unverified_runtime":["actual replacement lookup/loading is user-operated, not executed by this tool",
                                  "only native full-region single-level source and exact file CLUT keys are generated",
                                  "different runtime palettes, texture regions or mip chains may need separately observed keys",
                                  "this main-font pack does not replace PF network fonts, image-based UI text or movies"],
            "preview_entries":examples,"textures":[],"previews":[],
            "installation":"copy the SERIAL directory contents into the explicitly resolved PCSX2 Textures directory; installer/receipt handled separately"}
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{output.name}-",dir=output.parent) as temporary:
        stage=Path(temporary)/"pack"
        stage.mkdir()
        names=set()
        for name,data in textures.items():
            identity=tim2_replacement_identity(data)
            relative=Path(serial)/"replacements"/identity["filename"]
            if str(relative) in names:
                raise HdFontError("duplicate replacement filename")
            names.add(str(relative))
            row={"source_member":name,**identity,"path":relative.as_posix(),
                 "raw_peak_rgba":list(hd.peak_rgba[name]),
                 "mapped_rectangles_native":hd.replaced_rectangles[name],
                 "ascii_rectangles_native":hd.ascii_rectangles[name],
                 "png":_save_png(hd.images[name],stage/relative)}
            report["textures"].append(row)
        for name,pixels in (("native-1x.png",native),("native-4x-nearest.png",nearest),("outline-4x.png",high)):
            relative=Path("previews")/name
            report["previews"].append({"path":relative.as_posix(),**_save_png(pixels,stage/relative)})
        width=max(nearest.width,high.width)+32
        comparison=Image.new("RGBA",(width,nearest.height+high.height+96),(14,20,24,255))
        draw=ImageDraw.Draw(comparison)
        draw.text((16,10),"Native atlas (1x bitmap, 4x nearest display)",fill="white")
        comparison.alpha_composite(nearest,(16,32))
        draw.text((16,nearest.height+52),"Optional 4x replacement (fresh pinned outlines, unchanged native UV/layout)",fill="white")
        comparison.alpha_composite(high,(16,nearest.height+74))
        relative=Path("previews/comparison.png")
        report["previews"].append({"path":relative.as_posix(),**_save_png(comparison,stage/relative)})
        path=stage/"hd-font-manifest.json"
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf8",newline="\n")
        if json.loads(path.read_text(encoding="utf8")) != report:
            raise HdFontError("HD manifest readback differs")
        stage.rename(output)
    # Reopen published names, including every PNG, rather than trusting a rename.
    verify_pack(output)
    return report


def verify_pack(output: Path) -> dict:
    from PIL import Image
    report=json.loads((output/"hd-font-manifest.json").read_text(encoding="utf8"))
    root=output.resolve()
    for row in report["textures"]+report["previews"]:
        path=(root/row["path"]).resolve()
        if not path.is_relative_to(root):
            raise HdFontError("HD manifest output path escapes pack")
        expected=row.get("png",row)
        if path.stat().st_size != expected["size"] or sha256_file(path) != expected["sha256"]:
            raise HdFontError("published HD file identity mismatch")
        with Image.open(path) as pixels:
            pixels.load()
            if pixels.mode!="RGBA" or pixels.size!=(expected["width"],expected["height"]):
                raise HdFontError("published HD PNG profile differs")
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iso",required=True,type=Path)
    parser.add_argument("--manifest",required=True,type=Path)
    parser.add_argument("--font",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    report=build_pack(args.iso,args.manifest,args.font,args.output)
    print(f"HD_FONT PASS pages={len(report['textures'])} glyphs={report['mapped_glyphs']} ascii={report['ascii_outline_glyphs']} scale=4 padding=transparent native_mapping=exact png_readback=exact runtime=user-test")
    print(args.output.resolve()/"hd-font-manifest.json")


if __name__=="__main__":
    main()
