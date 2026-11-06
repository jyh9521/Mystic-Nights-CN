"""Source-bound authored HD layers over a reversible glyph-free native base.

The caller supplies reviewed glyph RGBA pixels, not a desktop-font name. This
module neither generates glyphs nor silently scales up localized native ink.
Only the unchanged material is nearest-scaled. Replacement keys always refer
to the final native TIM2, before material removal and HD authored layers.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath
import re

from .artwork import apply_artwork
from .hd_font import raw_atlas,tim2_replacement_identity
from .iso9660 import sha256_file
from .resources import parse_res


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _rect(value,width,height):
    if (not isinstance(value,list) or len(value)!=4 or any(type(v) is not int for v in value)):
        raise ValueError('HD artwork rectangle requires four integers')
    x,y,w,h=value
    if x<0 or y<0 or w<1 or h<1 or x+w>width or y+h>height:
        raise ValueError('HD artwork rectangle outside image')
    return x,y,w,h


def _intersects(a,b):
    return max(a[0],b[0])<min(a[0]+a[2],b[0]+b[2]) and max(a[1],b[1])<min(a[1]+a[3],b[1]+b[3])


def _rle_image(runs,width,height):
    from PIL import Image
    if not isinstance(runs,list) or not runs:
        raise ValueError('HD artwork layer RLE is empty')
    data=bytearray();count=0;limit=width*height
    for run in runs:
        if not isinstance(run,list) or len(run)!=2:
            raise ValueError('Invalid HD artwork RLE run')
        amount,color=run
        if type(amount) is not int or amount<1 or count+amount>limit:
            raise ValueError('HD artwork RLE run exceeds rectangle')
        if not isinstance(color,list) or len(color)!=4 or any(type(v) is not int or not 0<=v<=255 for v in color):
            raise ValueError('HD artwork RLE color must be four raw RGBA bytes')
        data.extend(bytes(color)*amount);count+=amount
    if count!=limit:
        raise ValueError('HD artwork RLE does not fill rectangle exactly')
    return Image.frombytes('RGBA',(width,height),bytes(data))


def _difference_mask(a,b):
    from PIL import ImageChops
    difference=ImageChops.difference(a,b)
    result=difference.getchannel('R')
    for channel in ('G','B','A'):
        result=ImageChops.lighter(result,difference.getchannel(channel))
    return result.point([0]+[255]*255)


def build_texture(source: bytes,recipe: dict,*,scale: int=4):
    """Return raw RGBA atlas + proof; alpha is never display-normalized here."""
    from PIL import Image,ImageChops,ImageDraw
    if scale!=4 or type(scale) is not int:
        raise ValueError('HD artwork requires scale=4')
    if not isinstance(recipe,dict) or recipe.get('source_sha256')!=_sha(source):
        raise ValueError('HD artwork native source SHA-256 mismatch')
    texa=recipe.get('clut16_texa')
    identity=tim2_replacement_identity(source,hash_function=lambda data:0,clut16_texa=texa)
    native=raw_atlas(source,clut16_texa=texa)
    width,height=native.width*scale,native.height*scale
    if max(width,height)>16384:
        raise ValueError('HD artwork dimensions exceed supported bounds')
    rectangles=recipe.get('allowed_hd_rectangles')
    if not isinstance(rectangles,list) or not rectangles:
        raise ValueError('HD artwork requires allowed HD rectangles')
    allowed=Image.new('L',(width,height)); draw=ImageDraw.Draw(allowed)
    for value in rectangles:
        x,y,w,h=_rect(value,width,height)
        draw.rectangle((x,y,x+w-1,y+h-1),fill=255)
    delta=recipe.get('base_delta')
    if not isinstance(delta,dict):
        raise ValueError('HD artwork requires a source-bound native base delta')
    base_bytes=apply_artwork(source,delta)
    if apply_artwork(base_bytes,delta,reverse=True)!=source:
        raise ValueError('HD artwork base delta roundtrip mismatch')
    base=raw_atlas(base_bytes,clut16_texa=texa).resize((width,height),Image.Resampling.NEAREST)
    original=native.resize((width,height),Image.Resampling.NEAREST)
    outside=ImageChops.invert(allowed)
    if ImageChops.multiply(_difference_mask(base,original),outside).getbbox():
        raise ValueError('HD artwork base material changed outside allowed HD regions')
    layers=recipe.get('layers')
    if not isinstance(layers,list) or not layers:
        raise ValueError('HD artwork requires authored pixel layers')
    image=base.copy(); ids=set();regions=[];layer_reports=[]
    layer_mask=Image.new('L',(width,height));layer_draw=ImageDraw.Draw(layer_mask)
    # A text-free base can accidentally be the original *lettered* texture.
    # Track replacement coverage, not RGB differences: a fresh transparent
    # pixel also replaces the old pixel, whereas a half-covered mask does not.
    replacement_coverage=Image.new('L',(width,height))
    for layer in layers:
        if not isinstance(layer,dict):
            raise ValueError('Invalid HD artwork layer')
        name=layer.get('id')
        if not isinstance(name,str) or not name or name in ids or any(ord(c)<32 for c in name):
            raise ValueError('HD artwork layer ids missing/duplicate')
        ids.add(name)
        rect=_rect(layer.get('rect'),width,height);x,y,w,h=rect
        if allowed.crop((x,y,x+w,y+h)).getextrema()!=(255,255):
            raise ValueError('HD artwork layer rectangle outside allowed HD regions')
        if any(_intersects(rect,other) for other in regions):
            raise ValueError('HD artwork layer rectangles overlap')
        regions.append(rect)
        authored=_rle_image(layer.get('pixels_rle'),w,h)
        mode=layer.get('mode')
        if mode=='replace-region':
            result=authored
            coverage=Image.new('L',(w,h),255)
        elif mode in ('rgb-mask-keep-alpha','rgba-mask'):
            peak=layer.get('alpha_peak')
            if mode=='rgba-mask' and (type(peak) is not int or not 0<=peak<=255):
                raise ValueError('HD artwork rgba-mask requires raw byte alpha_peak')
            material=image.crop((x,y,x+w,y+h));old=material.tobytes();glyph=authored.tobytes()
            mixed=bytearray(old)
            for offset in range(0,len(old),4):
                coverage=glyph[offset+3]
                for channel in range(3):
                    mixed[offset+channel]=(glyph[offset+channel]*coverage+old[offset+channel]*(255-coverage)+127)//255
                if mode=='rgba-mask':
                    mixed[offset+3]=(peak*coverage+old[offset+3]*(255-coverage)+127)//255
            result=Image.frombytes('RGBA',(w,h),bytes(mixed))
            coverage=authored.getchannel('A')
            if mode=='rgb-mask-keep-alpha' and result.getchannel('A').tobytes()!=material.getchannel('A').tobytes():
                raise ValueError('HD artwork RGB mask altered base alpha')
        else:
            raise ValueError('Unknown HD artwork layer mode')
        image.paste(result,(x,y));layer_draw.rectangle((x,y,x+w-1,y+h-1),fill=255)
        replacement_coverage.paste(coverage,(x,y))
        layer_reports.append({'id':name,'rect':list(rect),'mode':mode,
                              **({'alpha_peak':layer['alpha_peak']} if mode=='rgba-mask' else {}),
                              'authored_rgba_sha256':_sha(authored.tobytes()),
                              'rendered_rgba_sha256':_sha(result.tobytes())})
    required=recipe.get('full_coverage_regions',[])
    if not isinstance(required,list):
        raise ValueError('HD artwork full coverage regions require a list')
    for value in required:
        x,y,w,h=_rect(value,width,height)
        if allowed.crop((x,y,x+w,y+h)).getextrema()!=(255,255):
            raise ValueError('HD artwork full coverage region outside allowed HD regions')
        if replacement_coverage.crop((x,y,x+w,y+h)).getextrema()!=(255,255):
            raise ValueError('HD artwork full coverage region reuses old base pixels')
    final_difference=_difference_mask(image,original)
    if ImageChops.multiply(final_difference,outside).getbbox():
        raise ValueError('HD artwork output changed protected native pixels')
    base_difference=_difference_mask(image,base)
    if ImageChops.multiply(base_difference,ImageChops.invert(layer_mask)).getbbox():
        raise ValueError('HD artwork output changed pixels outside authored layers')
    return image,{'native_raw_rgba_sha256':_sha(native.tobytes()),
                  'base_native_sha256':_sha(base_bytes),'base_raw_hd_rgba_sha256':_sha(base.tobytes()),
                  'output_raw_hd_rgba_sha256':_sha(image.tobytes()),
                  'base_delta_sha256':_sha(json.dumps(delta,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf8')),
                  'base_roundtrip':'byte-identical','outside_allowed':'raw RGBA byte-identical to final-native nearest',
                  'outside_layers':'raw RGBA byte-identical to glyph-free-base nearest',
                  'changed_hd_pixels':final_difference.histogram()[255],
                  'full_coverage_regions':required,
                  'layers':layer_reports,'native_width':identity['width'],'native_height':identity['height']}


def _resource_path(value):
    if not isinstance(value,str) or '\\' in value or ':' in value or any(ord(c)<32 for c in value):
        raise ValueError('Invalid HD artwork resource path')
    path=PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or str(path)!=value or not path.parts:
        raise ValueError('Noncanonical HD artwork resource path')
    return value


def bind_sources(image,manifest: dict,recipe: dict,version: dict):
    """Bind recipe rows to the exact final ISO/build manifest and RES members."""
    if (recipe.get('format')!='hd-artwork-recipe' or type(recipe.get('version')) is not int
            or recipe['version']!=1 or type(recipe.get('scale')) is not int or recipe['scale']!=4):
        raise ValueError('Unsupported HD artwork recipe format/scale')
    serial=recipe.get('serial')
    if (not isinstance(serial,str) or not re.fullmatch(r'[A-Z]{4}-[0-9]{5}',serial)
            or serial!=version.get('serial')):
        raise ValueError('HD artwork recipe serial differs from supported game')
    if manifest.get('original')!=version.get('iso'):
        raise ValueError('HD artwork build manifest original ISO identity differs')
    modified=manifest.get('modified',{})
    if (image.size!=version['iso']['size'] or modified.get('size')!=image.size
            or modified.get('sha256')!=sha256_file(image.path)):
        raise ValueError('HD artwork final ISO differs from build manifest')
    cnf=image.read('SYSTEM.CNF');expected=version['files']['SYSTEM.CNF']
    if len(cnf)!=expected['size'] or _sha(cnf)!=expected['sha256']:
        raise ValueError('HD artwork SYSTEM.CNF version identity differs')
    changes={}
    for row in manifest.get('changed_files',[]):
        resource=_resource_path(row.get('path'))
        if resource in changes:
            raise ValueError('Duplicate HD artwork build-manifest resource')
        changes[resource]=row
    textures=recipe.get('textures')
    if not isinstance(textures,list) or not textures:
        raise ValueError('HD artwork recipe has no textures')
    resources={};archives={};seen=[];bound=[]
    for row in textures:
        if not isinstance(row,dict) or not isinstance(row.get('reference'),dict):
            raise ValueError('Invalid HD artwork texture reference')
        ref=row['reference'];resource=_resource_path(ref.get('resource'))
        member=ref.get('member');offset=ref.get('offset');size=ref.get('size')
        if (not isinstance(member,str) or not member or any(ord(c)<32 for c in member)
                or any(c in member for c in '/\\:') or type(offset) is not int or offset<0
                or type(size) is not int or size<1):
            raise ValueError('Invalid HD artwork member reference fields')
        entry=image.get(resource)
        if getattr(entry,'path',resource)!=resource:
            raise ValueError('HD artwork resource path aliases canonical ISO entry')
        physical_start=entry.offset+offset
        if any(physical_start<end and start<physical_start+size for start,end in seen):
            raise ValueError('Duplicate/overlapping HD artwork physical references')
        seen.append((physical_start,physical_start+size))
        if resource not in resources:
            data=image.read(resource);entry=image.get(resource)
            if resource in changes:
                changed=changes[resource]
                if (changed.get('size')!=len(data) or changed.get('sha256')!=_sha(data)
                        or changed.get('offset')!=entry.offset):
                    raise ValueError('HD artwork resource differs from build manifest')
            resources[resource]=data;archives[resource]=parse_res(data)
        archive=archives[resource]
        matches=[entry for entry in archive.entries if entry.name==member and entry.offset==offset and entry.size==size]
        if len(matches)!=1:
            raise ValueError('HD artwork reference does not match exact parsed RES member')
        source=archive.read(matches[0])
        if row.get('source_sha256')!=_sha(source):
            raise ValueError('HD artwork referenced final-native TIM2 SHA-256 differs')
        bound.append((row,source))
    return bound
