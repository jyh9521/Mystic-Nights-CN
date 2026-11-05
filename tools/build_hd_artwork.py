#!/usr/bin/env python3
"""Build a fresh optional authored HD artwork pack from a final localized ISO."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from _bootstrap import ROOT
from mysticnights.hd_artwork import bind_sources,build_texture
from mysticnights.hd_font import tim2_replacement_identity
from mysticnights.iso9660 import IsoImage,sha256_file


def build_pack(iso_path:Path,manifest_path:Path,recipe_path:Path,output:Path,*,hash_function=None):
    from PIL import Image
    output=output.resolve()
    if output.exists():
        raise FileExistsError('HD artwork output must be a new directory')
    manifest_bytes=manifest_path.read_bytes();recipe_bytes=recipe_path.read_bytes()
    manifest=json.loads(manifest_bytes);recipe=json.loads(recipe_bytes)
    version=json.loads((ROOT/'assets/game-version.json').read_text(encoding='utf8'))
    bound=bind_sources(IsoImage(iso_path),manifest,recipe,version)
    report={'format':'pcsx2-hd-artwork-pack','version':1,'pcsx2_source_revision':'v2.9.155',
            'serial':recipe['serial'],'scale':recipe['scale'],'locale':manifest.get('locale'),
            'source_iso':manifest['modified'],
            'source_manifest_sha256':hashlib.sha256(manifest_bytes).hexdigest(),
            'source_recipe_sha256':hashlib.sha256(recipe_bytes).hexdigest(),
            'pixel_policy':'authored glyph RLE only; raw RGBA; unchanged base material nearest-scaled',
            'unverified_runtime':['actual replacement loading is user-operated; no emulator launched',
                                  'only full-region single-level exact-source-CLUT keys are generated',
                                  'other runtime palettes, regions or mip chains need separately observed keys'],
            'textures':[]}
    rendered=[];seen=set()
    for row,source in bound:
        identity=tim2_replacement_identity(source,hash_function=hash_function)
        if identity['filename'] in seen:
            raise ValueError('Duplicate HD artwork replacement filename')
        seen.add(identity['filename'])
        pixels,proof=build_texture(source,row,scale=recipe['scale'])
        relative=Path(recipe['serial'])/'replacements'/identity['filename']
        record={**identity,'path':relative.as_posix(),'reference':row['reference'],'proof':proof}
        rendered.append((pixels,relative,record))
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f'.{output.name}-',dir=output.parent) as temporary:
        stage=Path(temporary)/'pack';stage.mkdir()
        for pixels,relative,record in rendered:
            path=stage/relative;path.parent.mkdir(parents=True,exist_ok=True)
            pixels.save(path,format='PNG',compress_level=9)
            with Image.open(path) as reopened:
                reopened.load()
                if reopened.mode!='RGBA' or reopened.size!=pixels.size or reopened.tobytes()!=pixels.tobytes():
                    raise ValueError('HD artwork PNG pixel roundtrip mismatch')
            record['png']={'sha256':sha256_file(path),'size':path.stat().st_size,
                           'width':pixels.width,'height':pixels.height,
                           'raw_rgba_sha256':hashlib.sha256(pixels.tobytes()).hexdigest()}
            report['textures'].append(record)
        path=stage/'hd-artwork-manifest.json'
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
        if json.loads(path.read_text(encoding='utf8'))!=report:
            raise ValueError('HD artwork manifest readback mismatch')
        stage.rename(output)
    verify_pack(output)
    return report


def verify_pack(output:Path):
    from PIL import Image
    root=output.resolve();report=json.loads((root/'hd-artwork-manifest.json').read_text(encoding='utf8'))
    if report.get('format')!='pcsx2-hd-artwork-pack' or report.get('version')!=1:
        raise ValueError('Unknown HD artwork pack')
    seen=set()
    for row in report['textures']:
        path=(root/row['path']).resolve()
        if not path.is_relative_to(root) or path in seen:
            raise ValueError('HD artwork output path escaped/duplicated')
        seen.add(path);png=row['png']
        if path.stat().st_size!=png['size'] or sha256_file(path)!=png['sha256']:
            raise ValueError('HD artwork published PNG identity mismatch')
        with Image.open(path) as image:
            image.load()
            if (image.mode!='RGBA' or image.size!=(png['width'],png['height'])
                    or hashlib.sha256(image.tobytes()).hexdigest()!=png['raw_rgba_sha256']):
                raise ValueError('HD artwork published raw pixels mismatch')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('iso','manifest','recipe','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    report=build_pack(args.iso,args.manifest,args.recipe,args.output)
    layers=sum(len(row['proof']['layers']) for row in report['textures'])
    print(f"HD_ARTWORK PASS textures={len(report['textures'])} layers={layers} scale=4 protected=exact png_roundtrip=exact runtime=user-test")
    print(args.output.resolve()/'hd-artwork-manifest.json')


if __name__=='__main__':main()
