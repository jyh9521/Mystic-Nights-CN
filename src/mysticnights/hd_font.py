"""Optional, exact-palette PCSX2 replacements for the existing main font.

The source atlas, not the replacement PNG, determines the filename. The hash
profile follows PCSX2 v2.9.155's full-region, single-level PSMT8 path. Runtime
palette changes, mip chains and source regions require a separately observed
key; this module deliberately does not manufacture wildcard names for them.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
from pathlib import Path
import struct
from typing import Callable, Mapping

from .font import (_coverage_lut, allocate_codes, common_baseline_shift,
                   downsample_coverage, parse_fnt, parse_tim2, resource_hash, Tim2)
from .iso9660 import sha256_file


class HdFontError(ValueError):
    """A source identity, layout or supported replacement profile disagrees."""


def swizzle8_offset(x: int, y: int) -> int:
    """Byte offset inside one 16x16 PSMT8 block (all 256 entries verified)."""
    if type(x) is not int or type(y) is not int or not 0 <= x < 16 or not 0 <= y < 16:
        raise HdFontError("PSMT8 block coordinates must be integers in 0..15")
    value = 0
    for bit, basis in enumerate((4, 16, 32, 2)):
        if x & (1 << bit):
            value ^= basis
    for bit, basis in enumerate((8, 33, 96, 128)):
        if y & (1 << bit):
            value ^= basis
    return value


_SWIZZLE8 = tuple(swizzle8_offset(x, y) for y in range(16) for x in range(16))


def indexed_hash_payload(indices: bytes, width: int, height: int) -> bytes:
    """Concatenate physical blocks in logical block-row order, like HashTextureLevel.

    This is not a GS-memory page swizzle: block addresses are walked by logical
    coordinates before hashing, so only the within-block ordering is relevant.
    """
    if (type(width) is not int or type(height) is not int or width < 16 or height < 16
            or width % 16 or height % 16 or len(indices) != width * height):
        raise HdFontError("full PSMT8 hash needs complete 16x16 blocks and exact pixel length")
    output = bytearray(len(indices))
    position = 0
    for top in range(0, height, 16):
        for left in range(0, width, 16):
            for y in range(16):
                start = (top + y) * width + left
                for x in range(16):
                    output[position + _SWIZZLE8[y * 16 + x]] = indices[start + x]
            position += 256
    return bytes(output)


def replacement_bits(psm: int, tw: int, th: int) -> int:
    """TextureName packed fields; indexed PSMT8/CLUT32 has no TEXA field."""
    if (type(psm) is not int or not 0 <= psm < 64 or type(tw) is not int
            or not 0 <= tw < 16 or type(th) is not int or not 0 <= th < 16):
        raise HdFontError("invalid replacement TextureName bit fields")
    return psm | (tw << 6) | (th << 10)


def format_replacement_name(texture_hash: int, palette_hash: int, bits: int) -> str:
    for value, limit in ((texture_hash, 1 << 64), (palette_hash, 1 << 64), (bits, 1 << 32)):
        if type(value) is not int or not 0 <= value < limit:
            raise HdFontError("replacement filename integer outside supported range")
    return f"{texture_hash:x}-{palette_hash:x}-{bits:08x}.png"


def _xxh3(data: bytes) -> int:
    try:
        import xxhash
    except ImportError as exc:
        raise HdFontError("optional HD build requires requirements-hd.txt (xxhash)") from exc
    return xxhash.xxh3_64_intdigest(data)


def _replacement_info(data: bytes, clut16_texa: Mapping | None = None) -> Tim2:
    """Read a supported raw CLUT; CLUT16 always requires an explicit TEXA.

    GSClut::Expand16 uses RGB5 << 3, not normalized 5-to-8 bit values. TEXA
    controls alpha during expansion. A palette-less wildcard or a guessed
    default would silently accept another runtime palette, so neither is used.
    """
    if len(data) < 64 or data[34] not in (1, 0x81):
        if clut16_texa is not None:
            raise HdFontError("CLUT16 TEXA profile supplied for a non-CLUT16 TIM2")
        return parse_tim2(data)
    if (not isinstance(clut16_texa, Mapping) or set(clut16_texa) != {"ta0", "ta1", "aem"}
            or any(type(clut16_texa.get(key)) is not int or not 0 <= clut16_texa[key] <= 255
                   for key in ("ta0", "ta1"))
            or type(clut16_texa.get("aem")) is not bool):
        raise HdFontError("CLUT16 requires explicit byte ta0/ta1 and boolean aem TEXA profile")
    # AEM=false is the source-backed profile confirmed for these supplied
    # assets. Do not extrapolate unobserved zero-colour AEM behavior.
    if clut16_texa["aem"]:
        raise HdFontError("CLUT16 AEM=true is outside the verified replacement profile")
    if data[:8] != b"TIM2\x04\x00\x01\x00":
        raise HdFontError("unsupported CLUT16 TIM2 header")
    total, palette_length, pixels_length = struct.unpack_from("<III", data, 16)
    header_length, palette_count = struct.unpack_from("<HH", data, 28)
    picture_format, mipmaps, clut_type, image_type = data[32:36]
    width, height = struct.unpack_from("<HH", data, 36)
    tex0, = struct.unpack_from("<Q", data, 40)
    if (header_length != 48 or picture_format != 0 or mipmaps != 1 or image_type != 5
            or not width or not height or pixels_length != width * height
            or palette_count != 256 or palette_length != 512
            or total != header_length + pixels_length + palette_length or len(data) != 16 + total
            or (tex0 >> 51) & 15 != 2 or (tex0 >> 55) & 63):
        raise HdFontError("unsupported CLUT16 TIM2 lengths/CSM1/CPSM2 profile")
    pixel_offset = 64
    palette_offset = pixel_offset + pixels_length
    colors = []
    for index in range(256):
        physical = index if clut_type & 0x80 else (
            (index & ~0x18) | ((index & 0x08) << 1) | ((index & 0x10) >> 1))
        value, = struct.unpack_from("<H", data, palette_offset + physical * 2)
        color = tuple(((value >> shift) & 31) << 3 for shift in (0, 5, 10))
        colors.append(color + (clut16_texa["ta1" if value & 0x8000 else "ta0"],))
    return Tim2(width, height, pixel_offset, pixels_length, palette_offset, palette_length, tuple(colors))


def tim2_replacement_identity(data: bytes, *, hash_function: Callable[[bytes], int] | None = None,
                              clut16_texa: Mapping | None = None) -> dict:
    """Exact key for a reviewed PSMT8/CLUT32 or explicit CLUT16 TIM2.

    Supports power-of-two dimensions >=16, including the 512x256 menu atlas.
    One level and the source CLUT are required; CLUT16 requires explicit TEXA.
    No inference from PNG appearance or a localized title is involved.
    """
    info = _replacement_info(data, clut16_texa)
    tex0, = struct.unpack_from("<Q", data, 40)
    psm, tw, th = (tex0 >> 20) & 63, (tex0 >> 26) & 15, (tex0 >> 30) & 15
    cpsm = (tex0 >> 51) & 15
    expected_cpsm = 2 if info.palette_length == 512 else 0
    if (psm != 19 or cpsm != expected_cpsm or (1 << tw, 1 << th) != (info.width, info.height)
            or min(info.width, info.height) < 16):
        raise HdFontError("TIM2 TEX0 must match supported full PSMT8 / exact CLUT dimensions")
    # A nonzero CSA selects a different palette segment at runtime. CSM must
    # agree with the verified CSM1 font/artwork profile (linear file CLUT is OK).
    if (tex0 >> 55) & 63:
        raise HdFontError("TIM2 TEX0 CSM/CSA outside verified palette profile")
    digest = hash_function or _xxh3
    payload = indexed_hash_payload(data[info.pixel_offset:info.palette_offset], info.width, info.height)
    palette = bytes(channel for color in info.palette for channel in color)
    texture_hash, palette_hash = digest(payload), digest(palette)
    bits = replacement_bits(psm, tw, th)
    result = {"texture_hash": f"{texture_hash:016x}", "palette_hash": f"{palette_hash:016x}",
            "bits": f"{bits:08x}", "filename": format_replacement_name(texture_hash, palette_hash, bits),
            "width": info.width, "height": info.height,
            "source_sha256": hashlib.sha256(data).hexdigest(),
            "hash_payload_sha256": hashlib.sha256(payload).hexdigest(),
            "raw_palette_sha256": hashlib.sha256(palette).hexdigest()}
    if expected_cpsm == 2:
        result["clut16_texa"] = dict(clut16_texa)
        result["clut16_rgb_expansion"] = "RGB5 << 3; source-backed GSClut Expand16 profile"
    return result


def raw_atlas(data: bytes, *, clut16_texa: Mapping | None = None):
    """Decode raw RGBA exactly; the replacement loader does not double alpha."""
    from PIL import Image
    info = _replacement_info(data, clut16_texa)
    rgba = bytes(c for index in data[info.pixel_offset:info.palette_offset] for c in info.palette[index])
    return Image.frombytes("RGBA", (info.width, info.height), rgba)


@dataclass(frozen=True)
class HdFontBuild:
    images: dict
    mapped_glyphs: int
    baseline_shift: int
    peak_rgba: dict
    replaced_rectangles: dict
    ascii_glyphs: int
    ascii_rectangles: dict
    cleared_padding_pixels_native: dict


def _ascii_outline_mask(char, glyph, source, face, scale):
    """Preserve the native ASCII core layout, not its low-resolution bitmap.

    ASCII metrics were drawn for a different face than the pinned locale face.
    Source core bounds retain its size/baseline (notably L2 and digits); fresh
    outline ink is area-resampled into those bounds. No outline is thresholded.
    """
    from PIL import Image, ImageDraw
    mask = Image.new("L", (glyph.width * scale, (glyph.height - 1) * scale))
    native = source.crop((glyph.x, glyph.y+1, glyph.x+glyph.width, glyph.y+glyph.height))
    alpha = native.getchannel("A")
    peak = max(alpha.tobytes(), default=0)
    if char.isspace():
        if peak:
            raise HdFontError("ASCII whitespace unexpectedly contains source ink")
        return mask
    # The bound is a source-layout measurement only. Low-opacity retail fringe
    # noise must not enlarge E/^ etc.; output outline AA remains continuous.
    bounds = alpha.point([255 if a * 2 >= peak and a else 0 for a in range(256)]).getbbox()
    if not peak or bounds is None:
        raise HdFontError(f"ASCII glyph has no source core layout: {char!r}")
    box = face.getbbox(char, anchor="ls")
    canvas = Image.new("L", (max(box[2]-box[0], 1)+8, max(box[3]-box[1], 1)+8))
    ImageDraw.Draw(canvas).text((4-box[0], 4-box[1]), char, font=face, fill=255, anchor="ls")
    ink = canvas.getbbox()
    if ink is None:
        raise HdFontError(f"blank ASCII outline glyph: {char!r}")
    left, top, right, bottom = (v * scale for v in bounds)
    fitted = canvas.crop(ink).resize((right-left, bottom-top), Image.Resampling.BOX)
    mask.paste(fitted, (left, top))
    return mask


def build_hd_atlases(fnt: bytes, textures: Mapping[str, bytes], mapping: Mapping[str, int],
                     font_data: bytes, expected_font_sha256: str, *, pixel_size: int,
                     scale: int = 4, native_raster_policy: dict | None = None,
                     ascii_outlines: bool = False) -> HdFontBuild:
    """Draw mapped glyphs from outlines at 4x; keep native FNT UV/layout intact."""
    from fontTools.ttLib import TTFont
    from PIL import Image, ImageDraw, ImageFont

    if hashlib.sha256(font_data).hexdigest() != expected_font_sha256.lower():
        raise HdFontError("outline font SHA-256 mismatch")
    if scale != 4 or type(pixel_size) is not int or not 1 <= pixel_size <= 64:
        raise HdFontError("HD font requires scale=4 and a valid native pixel size")
    if type(ascii_outlines) is not bool:
        raise HdFontError("ascii_outlines must be a boolean")
    glyphs = parse_fnt(fnt)
    # Reuse strict protected/ASCII/duplicate/missing-code checks, without adding codes.
    checked = allocate_codes([], glyphs, existing_mapping=mapping)
    if checked != dict(mapping) or not mapping:
        raise HdFontError("HD font needs the existing complete nonempty glyph map")
    names = {resource_hash(name): name for name in textures}
    if len(names) != len(textures):
        raise HdFontError("atlas name hash collision")
    infos = {name: parse_tim2(data) for name, data in textures.items()}
    for name, info in infos.items():
        if (info.width, info.height) != (256, 256):
            raise HdFontError("main font profile requires 256x256 native atlases")
        # Use an injected dummy digest to check TEX0 without importing xxhash.
        tim2_replacement_identity(textures[name], hash_function=lambda data: 0)
    by_code = {g.code: g for g in glyphs}
    ascii_chars = {chr(g.code): g.code for g in glyphs if 32 <= g.code <= 126} if ascii_outlines else {}
    with TTFont(io.BytesIO(font_data), lazy=True) as outline:
        cmap = outline.getBestCmap()
        if any(ord(c) not in cmap for c in dict(mapping, **ascii_chars)):
            raise HdFontError("outline font lacks mapped characters")
        ascender, upem = outline["OS/2"].sTypoAscender, outline["head"].unitsPerEm
    face = ImageFont.truetype(io.BytesIO(font_data), pixel_size * scale)
    baseline = round(pixel_size * scale * ascender / upem)
    bounds = []
    for char, code in mapping.items():
        glyph = by_code[code]
        if glyph.texture_hash not in names:
            raise HdFontError("FNT refers to an absent font atlas")
        cell_h = (glyph.height - 1) * scale
        nominal = baseline + (cell_h - pixel_size * scale) // 2
        box = face.getbbox(char, anchor="ls")
        bounds.append((nominal + box[1], nominal + box[3], cell_h))
    shift = common_baseline_shift(bounds)
    peaks = {name: info.palette[_coverage_lut(info.palette)[255]] for name, info in infos.items()}
    images = {name: raw_atlas(data).resize((256*scale, 256*scale), Image.Resampling.NEAREST)
              for name, data in textures.items()}
    sources = {name: raw_atlas(data) for name, data in textures.items()}
    occupied = {name: set() for name in textures}
    protected = {name: set() for name in textures}
    sampled = {name: set() for name in textures}
    mapped_codes = set(mapping.values())
    outlined_codes = mapped_codes | set(ascii_chars.values())
    for glyph in glyphs:
        if glyph.texture_hash not in names:
            raise HdFontError("FNT refers to an absent font atlas")
        name = names[glyph.texture_hash]
        if glyph.x + glyph.width > infos[name].width or glyph.y + glyph.height > infos[name].height:
            raise HdFontError("FNT glyph rectangle exceeds native atlas")
        sampled[name].update((x,y) for y in range(glyph.y+1,glyph.y+glyph.height)
                             for x in range(glyph.x,glyph.x+glyph.width))
        if glyph.code not in outlined_codes:
            protected[names[glyph.texture_hash]].update(
                (x,y) for y in range(glyph.y,glyph.y+glyph.height)
                for x in range(glyph.x,glyph.x+glyph.width))
    rectangles = {name: [] for name in textures}
    for char, code in sorted(mapping.items(), key=lambda item: item[1]):
        glyph = by_code[code]
        name = names[glyph.texture_hash]
        info = infos[name]
        if glyph.x + glyph.width > info.width or glyph.y + glyph.height > info.height:
            raise HdFontError("FNT glyph rectangle exceeds native atlas")
        area = {(x,y) for y in range(glyph.y, glyph.y+glyph.height)
                for x in range(glyph.x,glyph.x+glyph.width)}
        if occupied[name] & area or protected[name] & area:
            raise HdFontError("mapped FNT rectangle overlaps another mapped/protected glyph")
        occupied[name].update(area)
        w, h = glyph.width * scale, (glyph.height - 1) * scale
        box = face.getbbox(char, anchor="ls")
        x = round((w - face.getlength(char)) / 2)
        y = baseline + (h - pixel_size * scale) // 2 + shift
        if x+box[0] < 0 or x+box[2] > w or y+box[1] < 0 or y+box[3] > h:
            raise HdFontError(f"outline exceeds existing glyph cell: {char!r}")
        mask = Image.new("L", (w,h))
        ImageDraw.Draw(mask).text((x,y),char,font=face,fill=255,anchor="ls")
        if not mask.getbbox() and not char.isspace():
            raise HdFontError(f"blank outline glyph: {char!r}")
        # The build's mapping must describe the actual final native cells, not
        # merely be a plausible dictionary paired with an unrelated ISO.
        native_mask = downsample_coverage(mask, (glyph.width,glyph.height-1),native_raster_policy)
        lut = _coverage_lut(info.palette)
        expected_rows = [bytes([lut[0]])*glyph.width] + [
            bytes(lut[v] for v in native_mask.tobytes()[row*glyph.width:(row+1)*glyph.width])
            for row in range(glyph.height-1)]
        for row,expected in enumerate(expected_rows):
            start=info.pixel_offset+(glyph.y+row)*info.width+glyph.x
            if textures[name][start:start+glyph.width] != expected:
                raise HdFontError(f"native atlas does not match final manifest mapping/raster: {char!r}")
        r,g,b,a = peaks[name]
        cell = Image.new("RGBA", (w,h), (r,g,b,0))
        cell.putalpha(mask.point([round(v*a/255) for v in range(256)]))
        left, top = glyph.x*scale, glyph.y*scale
        images[name].paste((0,0,0,0),(left,top,left+w,top+glyph.height*scale))
        images[name].paste(cell,(left,top+scale))
        rectangles[name].append([glyph.x,glyph.y,glyph.width,glyph.height])
    ascii_rectangles = {name: [] for name in textures}
    ascii_face = ImageFont.truetype(io.BytesIO(font_data), pixel_size * scale * 4)
    for char, code in sorted(ascii_chars.items(), key=lambda item: item[1]):
        glyph = by_code[code]
        name = names[glyph.texture_hash]
        area = {(x,y) for y in range(glyph.y,glyph.y+glyph.height)
                for x in range(glyph.x,glyph.x+glyph.width)}
        if occupied[name] & area or protected[name] & area:
            raise HdFontError("ASCII FNT rectangle overlaps another outlined/protected glyph")
        occupied[name].update(area)
        mask = _ascii_outline_mask(char, glyph, sources[name], ascii_face, scale)
        r,g,b,a = peaks[name]
        cell = Image.new("RGBA", mask.size, (r,g,b,0))
        cell.putalpha(mask.point([round(v*a/255) for v in range(256)]))
        images[name].paste(cell, (glyph.x*scale,(glyph.y+1)*scale))
        ascii_rectangles[name].append([glyph.x,glyph.y,glyph.width,glyph.height])
    cleared = {}
    # Integer FST UV endpoints interpolate through the one-native-pixel gaps.
    # Those gaps are not referenced by *any* y+1/h-1 runtime glyph rectangle,
    # but the retail sheet contains old fringe ink there. Clear only unowned
    # texels; do not threshold the new outlines or edit protected sampled ink.
    for name, image in images.items():
        padding = Image.new("L", (256,256), 255)
        values = padding.load()
        for x,y in sampled[name]:
            values[x,y] = 0
        cleared[name] = sum(1 for y in range(256) for x in range(256)
                            if (x,y) not in sampled[name] and sources[name].getpixel((x,y))[3])
        image.paste((0,0,0,0), (0,0), padding.resize(image.size, Image.Resampling.NEAREST))
    # Independently prove protected *sampled* source cells remain exact, and
    # every unreferenced padding texel is transparent at the replacement scale.
    for name, image in images.items():
        source = sources[name]
        for y in range(256):
            for x in range(256):
                block = image.crop((x*scale,y*scale,(x+1)*scale,(y+1)*scale))
                if (x,y) not in sampled[name]:
                    if block.getchannel("A").getbbox() is not None:
                        raise HdFontError("unreferenced font padding is not transparent")
                elif (x,y) not in occupied[name]:
                    color = source.getpixel((x,y))
                    if block.getcolors() != [(scale*scale,color)]:
                        raise HdFontError("unmapped font pixel changed")
    return HdFontBuild(images,len(mapping),shift,peaks,rectangles,len(ascii_chars),ascii_rectangles,cleared)


def validate_inputs(iso_path: Path, manifest: dict, font_data: bytes, font_spec: dict,
                    version: dict, system: bytes, system_cnf: bytes) -> None:
    """Bind optional output to the exact final ISO/manifest and pinned outline."""
    original, modified = manifest.get("original"), manifest.get("modified", {})
    if original != version["iso"]:
        raise HdFontError("manifest original ISO identity is unsupported")
    if (modified.get("size") != iso_path.stat().st_size
            or modified.get("sha256") != sha256_file(iso_path)):
        raise HdFontError("final ISO differs from build manifest")
    font = manifest.get("font", {})
    digest = hashlib.sha256(font_data).hexdigest()
    if digest != font.get("sha256") or digest != font_spec.get("sha256"):
        raise HdFontError("font bytes, build manifest and pinned font source disagree")
    if set(font.get("mapping",{}).values()) & set(font.get("protected_codes",[])):
        raise HdFontError("font map overlaps protected source glyph codes")
    entries = [row for row in manifest.get("changed_files", []) if row.get("path") == "RES/SYSTEM.RES"]
    if (len(entries) != 1 or entries[0].get("size") != len(system)
            or entries[0].get("sha256") != hashlib.sha256(system).hexdigest()):
        raise HdFontError("SYSTEM.RES differs from final manifest")
    cnf = version["files"]["SYSTEM.CNF"]
    if len(system_cnf) != cnf["size"] or hashlib.sha256(system_cnf).hexdigest() != cnf["sha256"]:
        raise HdFontError("SYSTEM.CNF differs from supported game identity")


def render_hd_preview(fnt: bytes, textures: Mapping[str, bytes], hd_images: Mapping,
                       text: str, mapping: Mapping[str,int], *, hd: bool):
    """Actual atlas readback. Preview only converts PS2 alpha for screen display."""
    from PIL import Image
    glyphs = {g.code:g for g in parse_fnt(fnt)}
    names = {resource_hash(name):name for name in textures}
    factor = 4 if hd else 1
    atlases = hd_images if hd else {name:raw_atlas(data) for name,data in textures.items()}
    lines = text.split("\n")
    codes = [[ord(c) if ord(c)<128 else mapping[c] for c in line] for line in lines]
    width = max(sum(glyphs[c].width+1 for c in line) for line in codes)*factor
    line_h = max(g.height for g in glyphs.values())*factor
    image = Image.new("RGBA",(max(width,1),line_h*len(lines)))
    for row,line in enumerate(codes):
        left = 0
        for code in line:
            g = glyphs[code]
            cell=atlases[names[g.texture_hash]].crop((g.x*factor,(g.y+1)*factor,(g.x+g.width)*factor,(g.y+g.height)*factor))
            cell.putalpha(cell.getchannel("A").point([min(255,a*2) for a in range(256)]))
            image.alpha_composite(cell,(left,row*line_h))
            left+=(g.width+1)*factor
    return image
