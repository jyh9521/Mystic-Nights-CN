"""Mystic Nights' existing CP949-keyed, indexed-TIM2 font slots.

No executable patch is needed for a locale-specific glyph map: RenderString
combines a high-bit lead byte and the following byte into a big-endian key.
The retail binary has a fixed 2539-entry lookup, so this module preserves every
FNT record, atlas size, palette and non-allocated glyph.  Non-ASCII source text
that must remain visible should contribute its codes to ``forbidden_codes``.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
from pathlib import Path
import struct
from typing import Iterable, Mapping


class FontError(ValueError):
    """A font input or locale glyph map violates a verified invariant."""


def common_baseline_shift(bounds: Iterable[tuple[int, int, int]]) -> int:
    """Fit all (top, bottom, cell_height) intervals without individual shifts."""
    rows = list(bounds)
    if not rows:
        return 0
    if any(height < 1 or top > bottom for top, bottom, height in rows):
        raise FontError("Invalid outline bounds")
    lower = max(-top for top, _bottom, _height in rows)
    upper = min(height - bottom for _top, bottom, height in rows)
    if lower > upper:
        raise FontError("outline subset exceeds cell height at a common baseline; select a smaller pixel size")
    return min(max(0, lower), upper)


@dataclass(frozen=True)
class Glyph:
    texture_hash: int
    code: int
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class Tim2:
    width: int
    height: int
    pixel_offset: int
    pixel_length: int
    palette_offset: int
    palette_length: int
    palette: tuple[tuple[int, int, int, int], ...]


@dataclass(frozen=True)
class FontBuild:
    fnt: bytes
    textures: dict[str, bytes]
    mapping: dict[str, int]
    font_sha256: str


def resource_hash(name: str) -> int:
    """GetHashCode, VA 0x1488b0 in retail SCKA_200.55 (signed-byte djb2)."""
    value = 5381
    for byte in name.encode("ascii"):
        value = (value * 33 + byte) & 0xFFFFFFFF
    return value


def parse_fnt(data: bytes) -> tuple[Glyph, ...]:
    if len(data) < 4:
        raise FontError("truncated FNT count")
    count, = struct.unpack_from("<I", data)
    if not count or len(data) != 4 + count * 14:
        raise FontError("FNT count/length mismatch")
    result = tuple(Glyph(*struct.unpack_from("<IHHHHH", data, 4 + i * 14))
                   for i in range(count))
    codes = [g.code for g in result]
    if codes != sorted(set(codes)):
        raise FontError("FNT keys must be unique and sorted for binary lookup")
    for glyph in result:
        if not glyph.width or glyph.height < 2:
            raise FontError("invalid FNT glyph dimensions")
    return result


def parse_tim2(data: bytes) -> Tim2:
    """Read the verified font-only TIM2 profile, not arbitrary PS2 textures."""
    if len(data) < 64 or data[:8] != b"TIM2\x04\x00\x01\x00":
        raise FontError("unsupported font TIM2 header")
    total, palette_length, pixels_length = struct.unpack_from("<III", data, 16)
    header_length, palette_count = struct.unpack_from("<HH", data, 28)
    picture_format, mipmaps, clut_type, image_type = data[32:36]
    width, height = struct.unpack_from("<HH", data, 36)
    if (header_length != 48 or picture_format != 0 or mipmaps != 1
            or clut_type not in (3, 0x83) or image_type != 5):
        raise FontError("unsupported font TIM2 pixel/palette profile")
    if (not width or not height or pixels_length != width * height
            or palette_count != 256 or palette_length != 1024
            or total != header_length + pixels_length + palette_length
            or len(data) != 16 + total):
        raise FontError("font TIM2 lengths or palette bounds disagree")
    pixel_offset = 16 + header_length
    palette_offset = pixel_offset + pixels_length
    colors = []
    for index in range(256):
        # CLUT CSM1 exchanges bits 3 and 4; bit 7 signals a linear CLUT.
        physical = index if clut_type & 0x80 else (
            (index & ~0x18) | ((index & 0x08) << 1) | ((index & 0x10) >> 1))
        pos = palette_offset + physical * 4
        colors.append(tuple(data[pos:pos + 4]))
    return Tim2(width, height, pixel_offset, pixels_length, palette_offset,
                palette_length, tuple(colors))


def allocate_codes(texts: Iterable[str], glyphs: Iterable[Glyph], *,
                   forbidden_codes: Iterable[int] = (),
                   allowed_codes: Iterable[int] | None = None,
                   existing_mapping: Mapping[str, int] | None = None) -> dict[str, int]:
    """Allocate existing non-ASCII slots; preserve earlier assignments verbatim."""
    forbidden = set(forbidden_codes)
    available = {g.code for g in glyphs
                 if g.code > 0xFF and (g.code >> 8) & 0x80 and g.code & 0xFF}
    if allowed_codes is not None:
        available &= set(allowed_codes)
    mapping = dict(existing_mapping or {})
    if len(set(mapping.values())) != len(mapping):
        raise FontError("duplicate glyph-code assignment")
    for char, code in mapping.items():
        if len(char) != 1 or ord(char) < 128 or code not in available or code in forbidden:
            raise FontError(f"invalid or protected glyph assignment: {char!r}")
    needed = sorted({c for text in texts for c in text if ord(c) >= 128} - mapping.keys())
    remaining = sorted(available - forbidden - set(mapping.values()))
    if len(needed) > len(remaining):
        raise FontError(f"font slot overflow: need {len(needed)}, available {len(remaining)}")
    mapping.update(zip(needed, remaining))
    return mapping


def encode_text(text: str, mapping: Mapping[str, int]) -> bytes:
    """Encode mapped glyph keys without changing ASCII markup/control bytes."""
    result = bytearray()
    for char in text:
        if ord(char) < 128:
            if char == "\x00":
                raise FontError("embedded NUL in translation")
            result.append(ord(char))
        else:
            if char not in mapping:
                raise FontError(f"missing glyph assignment: {char!r}")
            code = mapping[char]
            if not isinstance(code, int) or not 0x8001 <= code <= 0xFFFF or not code & 0xFF:
                raise FontError(f"invalid two-byte glyph code for {char!r}")
            result.extend(code.to_bytes(2, "big"))
    return bytes(result)


def decode_text(data: bytes, mapping: Mapping[str, int]) -> str:
    """Strict inverse used by build verification; trailing NULs are not accepted."""
    reverse = {v: k for k, v in mapping.items()}
    if len(reverse) != len(mapping):
        raise FontError("duplicate glyph-code assignment")
    result = []
    pos = 0
    while pos < len(data):
        byte = data[pos]
        if byte == 0:
            raise FontError("unexpected NUL in encoded text")
        if not byte & 0x80:
            result.append(chr(byte))
            pos += 1
        else:
            if pos + 1 == len(data):
                raise FontError("truncated two-byte glyph")
            code = int.from_bytes(data[pos:pos + 2], "big")
            if code not in reverse:
                raise FontError(f"unknown glyph code: {code:04X}")
            result.append(reverse[code])
            pos += 2
    return "".join(result)


def _coverage_lut(palette: tuple[tuple[int, int, int, int], ...]) -> list[int]:
    # Keep original color/alpha ramps and original ASCII appearance. Quantize
    # against effective coverage rather than treating CLUT indices as gray levels.
    strength = [sum(c[:3]) * min(c[3], 128) for c in palette]
    peak = max(strength)
    transparent = [i for i, c in enumerate(palette) if c[3] == 0]
    if not peak or not transparent:
        raise FontError("font palette lacks transparent or visible entries")
    choices = [transparent[0]] + [i for i, s in enumerate(strength) if s > 0]
    return [min(choices, key=lambda i: (abs(strength[i] * 255 - level * peak), i))
            for level in range(256)]


def patch_glyphs(fnt: bytes, textures: Mapping[str, bytes], mapping: Mapping[str, int],
                 masks: Mapping[str, object]) -> dict[str, bytes]:
    """Insert supplied Pillow L-mode masks inside existing glyph rectangles only.

    Every mask must have width ``glyph.width`` and height ``glyph.height - 1``.
    LoadFont adds one to the stored Y and subtracts one from H; the top row is
    therefore retained as a transparent gutter. FNT and palette bytes do not change.
    """
    glyphs = {g.code: g for g in parse_fnt(fnt)}
    if len(set(mapping.values())) != len(mapping):
        raise FontError("duplicate glyph-code assignment")
    hashes = {resource_hash(name): name for name in textures}
    if len(hashes) != len(textures):
        raise FontError("texture hash collision")
    parsed = {name: parse_tim2(data) for name, data in textures.items()}
    output = {name: bytearray(data) for name, data in textures.items()}
    luts = {name: _coverage_lut(info.palette) for name, info in parsed.items()}
    for char, code in mapping.items():
        if code not in glyphs or code <= 0xFF:
            raise FontError(f"unknown or ASCII glyph slot: {code:04X}")
        glyph = glyphs[code]
        if glyph.texture_hash not in hashes:
            raise FontError(f"missing texture for {char!r}")
        name = hashes[glyph.texture_hash]
        info = parsed[name]
        if glyph.x + glyph.width > info.width or glyph.y + glyph.height > info.height:
            raise FontError("glyph rectangle outside texture")
        mask = masks.get(char)
        if (mask is None or getattr(mask, "mode", None) != "L"
                or getattr(mask, "size", None) != (glyph.width, glyph.height - 1)):
            raise FontError(f"wrong mask mode or dimensions for {char!r}")
        pixels = mask.tobytes()
        lut = luts[name]
        for row in range(glyph.height):
            start = info.pixel_offset + (glyph.y + row) * info.width + glyph.x
            values = bytes([lut[0]]) * glyph.width if row == 0 else bytes(
                lut[v] for v in pixels[(row - 1) * glyph.width:row * glyph.width])
            output[name][start:start + glyph.width] = values
    return {name: bytes(data) for name, data in output.items()}


def build_font(fnt: bytes, textures: Mapping[str, bytes], texts: Iterable[str],
               font_path: str | Path, expected_font_sha256: str, *,
               pixel_size: int = 13, forbidden_codes: Iterable[int] = (),
               allowed_codes: Iterable[int] | None = None,
               existing_mapping: Mapping[str, int] | None = None,
               raster_policy: dict | None = None) -> FontBuild:
    """Build a subset overlay using a hash-pinned, coverage-checked outline font."""
    from fontTools.ttLib import TTFont
    from PIL import Image, ImageDraw, ImageFont

    path = Path(font_path)
    font_data = path.read_bytes()
    digest = hashlib.sha256(font_data).hexdigest()
    if digest != expected_font_sha256.lower():
        raise FontError(f"font SHA-256 mismatch: {digest}")
    if not isinstance(pixel_size, int) or not 1 <= pixel_size <= 64:
        raise FontError("invalid font pixel size")
    glyphs = parse_fnt(fnt)
    mapping = allocate_codes(texts, glyphs, forbidden_codes=forbidden_codes,
                             allowed_codes=allowed_codes,
                             existing_mapping=existing_mapping)
    with TTFont(io.BytesIO(font_data), lazy=True) as face:
        cmap = face.getBestCmap()
        missing = [c for c in mapping if ord(c) not in cmap]
        units_per_em = face["head"].unitsPerEm
        typo_ascender = face["OS/2"].sTypoAscender
    if missing:
        raise FontError(f"outline font missing glyphs: {''.join(sorted(missing))}")
    # At 12-13 ppem, CJK hinting can inflate a 13-pixel character to 14 rows.
    # Supersampling avoids that clipping while retaining a common typographic
    # baseline (punctuation must not be individually vertically centered).
    supersample = 4
    face = ImageFont.truetype(io.BytesIO(font_data), pixel_size * supersample)
    baseline = round(pixel_size * supersample * typo_ascender / units_per_em)
    by_code = {g.code: g for g in glyphs}
    # Fit the *entire subset* to one common baseline. In particular a fullwidth
    # semicolon's descender must not be silently clipped or centered alone.
    bounds = []
    for char, code in mapping.items():
        cell_height = (by_code[code].height - 1) * supersample
        nominal = baseline + (cell_height - pixel_size * supersample) // 2
        box = face.getbbox(char, anchor="ls")
        bounds.append((nominal + box[1], nominal + box[3], cell_height))
    shift = common_baseline_shift(bounds)
    masks = {}
    for char, code in mapping.items():
        glyph = by_code[code]
        cell_width = glyph.width * supersample
        cell_height = (glyph.height - 1) * supersample
        box = face.getbbox(char, anchor="ls")
        x = round((cell_width - face.getlength(char)) / 2)
        y = baseline + (cell_height - pixel_size * supersample) // 2 + shift
        if (x + box[0] < 0 or x + box[2] > cell_width or y + box[1] < 0
                or y + box[3] > cell_height):
            raise FontError(f"outline glyph exceeds existing cell: {char!r} (bbox={box})")
        large = Image.new("L", (cell_width, cell_height))
        ImageDraw.Draw(large).text((x, y), char, font=face, fill=255, anchor="ls")
        mask = downsample_coverage(large, (glyph.width, glyph.height - 1), raster_policy)
        if not mask.getbbox() and not char.isspace():
            raise FontError(f"blank rendered glyph: {char!r}")
        masks[char] = mask
    patched = patch_glyphs(fnt, textures, mapping, masks)
    return FontBuild(fnt, patched, mapping, digest)


def downsample_coverage(large, size, policy=None):
    """Positive-area filtering avoids Lanczos sidelobes around small glyphs.

    Explicit edge thresholds are locale/build data. No JPEG, sharpening kernel,
    per-glyph baseline movement or palette replacement is involved.
    """
    from PIL import Image
    if policy is None:
        return large.resize(size, Image.Resampling.LANCZOS)
    if (set(policy) != {"filter", "edge_floor", "edge_ceiling"}
            or policy["filter"] != "box"
            or type(policy["edge_floor"]) is not int or type(policy["edge_ceiling"]) is not int
            or not 0 <= policy["edge_floor"] < policy["edge_ceiling"] <= 255):
        raise FontError("Invalid font raster policy")
    low, high = policy["edge_floor"], policy["edge_ceiling"]
    lut = [max(0, min(255, round((v-low)*255/(high-low)))) for v in range(256)]
    return large.resize(size, Image.Resampling.BOX).point(lut)


def render_preview(fnt: bytes, textures: Mapping[str, bytes], text: str,
                   mapping: Mapping[str, int], *, scale: int = 3):
    """Render the actual rebuilt atlas cells, not a separate desktop-font mockup."""
    from PIL import Image
    glyphs = {g.code: g for g in parse_fnt(fnt)}
    names = {resource_hash(name): name for name in textures}
    parsed = {name: parse_tim2(data) for name, data in textures.items()}
    line_height = max(g.height for g in glyphs.values())
    lines = text.split("\n")
    codes = [[ord(c) if ord(c) < 128 else mapping[c] for c in line] for line in lines]
    for line in codes:
        if any(c not in glyphs for c in line):
            raise FontError("preview contains an unsupported glyph")
    width = max((sum(glyphs[c].width + 1 for c in line) for line in codes), default=1)
    output = Image.new("RGBA", (max(width, 1), line_height * max(1, len(lines))), (0, 0, 0, 0))
    for row, line in enumerate(codes):
        x = 0
        for code in line:
            glyph = glyphs[code]
            name = names[glyph.texture_hash]
            info, data = parsed[name], textures[name]
            pixels = []
            for y in range(glyph.height - 1):
                start = info.pixel_offset + (glyph.y + y + 1) * info.width + glyph.x
                for value in data[start:start + glyph.width]:
                    r, g, b, a = info.palette[value]
                    pixels.append((r, g, b, min(a * 2, 255)))
            cell = Image.new("RGBA", (glyph.width, glyph.height - 1))
            cell.putdata(pixels)
            output.alpha_composite(cell, (x, row * line_height))
            x += glyph.width + 1
    return output.resize((output.width * scale, output.height * scale), Image.Resampling.NEAREST)
