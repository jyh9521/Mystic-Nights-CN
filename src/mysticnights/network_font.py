"""Sony libpfont PF subset reader and equal-size Unicode-slot font overlay.

The verified files are NETGUI/KOREAN.PF and EUROPEAN.PF, not TrueType fonts.
Only the shipped uncompressed 4-bit, 16-color profile is supported.  Headers,
Unicode ranges, lookup tables, metrics, palettes and glyph padding stay intact.
Missing target characters receive explicitly recorded, unprotected Hangul UCS-2
slots; encode_text must therefore be used when installing network UTF-8 text.
This finite source survey does not establish coverage of dynamic/user input.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
from pathlib import Path
import struct
from typing import Iterable, Mapping


KOREAN_SHA256 = "845cf99db8ae8df6b475ad8cc3e7f52cbba2d59a316b9c01d04142001613415a"
EUROPEAN_SHA256 = "d5457e8df9ab75d406eca52c2e07adaad06ecbef4cbc7dc29026296193562bae"
NETWORK_ELF_SHA256 = "ca08a4638d883d8f3216a04a3b1fc28ad14c58643671407420de03f5264ea5d1"


class NetworkFontError(ValueError):
    """The supplied data is not the verified PF profile or an edit is invalid."""


def _align16(value: int) -> int:
    return (value + 15) & ~15


def _slice(data: bytes, offset: int, size: int, label: str) -> bytes:
    if offset < 0 or size < 0 or offset + size > len(data):
        raise NetworkFontError(f"Out-of-bounds {label}")
    return data[offset:offset + size]


@dataclass(frozen=True)
class PFRange:
    first: int
    last: int
    map_base: int
    glyph_base: int


@dataclass(frozen=True)
class PFSubfont:
    index: int
    offset: int
    size: int
    flags: int
    width: int
    height: int
    ascent: int
    descent: int
    maximum_advance: int
    glyph_count: int
    glyph_stride: int
    bitmap_offset: int
    ranges: tuple[PFRange, ...]
    indices: tuple[int, ...]
    metrics: tuple[tuple[int, ...], ...]
    palette: tuple[tuple[int, int, int, int], ...]


@dataclass(frozen=True)
class PFGlyph:
    subfont: int
    index: int
    offset: int
    stride: int
    width: int
    height: int
    metrics: tuple[int, ...]

    @property
    def advance(self) -> int:
        return self.metrics[6]


@dataclass(frozen=True)
class PFFont:
    data: bytes
    name: str
    style: str
    ascent: int
    descent: int
    maximum_advance: int
    subfonts: tuple[PFSubfont, ...]
    glyphs: Mapping[int, PFGlyph]
    shadowed_codepoints: tuple[int, ...]


@dataclass(frozen=True)
class NetworkFontBuild:
    data: bytes
    mapping: dict[str, int]
    changed_glyphs: tuple[dict, ...]
    source_sha256: str
    font_sha256: str
    pixel_size: int


def parse_pf(data: bytes) -> PFFont:
    """Validate the complete shipped 4-bpp PF layout, including every lookup.

    UCS-2 keys may include the source font's surrogate-range button symbols;
    they are not advertised as valid Unicode scalar values for UTF-8 encoding.
    Later subfonts may repeat a key: the executable searches in file order.
    """
    if not isinstance(data, bytes) or len(data) < 96 or len(data) % 16:
        raise NetworkFontError("Truncated or unaligned PF")
    if struct.unpack_from("<4I", data) != (0, 0, len(data), 0):
        raise NetworkFontError("Unsupported PF version/size/reserved fields")
    names = []
    for offset in (16, 48):
        raw = data[offset:offset + 32]
        end = raw.find(b"\0")
        if end < 0 or any(raw[end:]):
            raise NetworkFontError("Malformed PF name")
        try:
            names.append(raw[:end].decode("ascii"))
        except UnicodeDecodeError as exc:
            raise NetworkFontError("Non-ASCII PF name") from exc
    ascent, descent, advance, reserved = struct.unpack_from("<4h", data, 80)
    if ascent <= 0 or descent > 0 or advance <= 0 or reserved:
        raise NetworkFontError("Unsupported PF global metrics")
    count = struct.unpack_from("<I", data, 88)[0]
    if not count or count > (len(data) - 92) // 4:
        raise NetworkFontError("Invalid PF subfont count")
    offsets = struct.unpack_from(f"<{count}I", data, 92)
    table_end = 92 + count * 4
    if (offsets[0] != _align16(table_end) or any(data[table_end:offsets[0]])
            or list(offsets) != sorted(set(offsets))
            or any(o % 16 or o + 96 > len(data) for o in offsets)):
        raise NetworkFontError("Invalid PF subfont offsets/padding")
    blocks, glyphs, shadowed = [], {}, []
    for number, offset in enumerate(offsets):
        end = offsets[number + 1] if number + 1 < count else len(data)
        size = end - offset
        block = _slice(data, offset, size, "subfont")
        header = struct.unpack_from("<24I", block)
        if header[:4] != (0, 0, size, 0) or header[4] not in (0, 8) or any(header[22:]):
            raise NetworkFontError("Unsupported subfont version/flags/reserved fields")
        if struct.unpack_from("<2f", block, 20) != (1.0, 1.0):
            raise NetworkFontError("Unsupported PF scale")
        width, height = struct.unpack_from("<2H", block, 28)
        asc, desc, max_advance, zero = struct.unpack_from("<4h", block, 32)
        if not 1 <= width <= 256 or not 1 <= height <= 256 or asc <= 0 or desc > 0 or max_advance <= 0 or zero:
            raise NetworkFontError("Invalid subfont dimensions/metrics")
        n_glyphs, bitmap, n_ranges, ranges_at, n_map, map_at, n_metrics, metrics_at, n_unknown, unknown_at, n_palette, palette_at = header[10:22]
        stride = _align16((width * height + 1) // 2)
        if not n_glyphs or n_glyphs > 65535 or bitmap != 96 or not n_ranges or not n_map:
            raise NetworkFontError("Invalid glyph/range/map counts")
        if (ranges_at != bitmap + stride * n_glyphs
                or map_at != ranges_at + 16 * n_ranges
                or metrics_at != _align16(map_at + 2 * n_map)
                or n_metrics != (n_glyphs if header[4] & 8 else 1)
                or n_unknown != 0 or unknown_at != metrics_at + 16 * n_metrics
                or n_palette != 16 or palette_at != unknown_at
                or size != palette_at + 64):
            raise NetworkFontError("Inconsistent PF table layout or unsupported auxiliary table")
        _slice(block, bitmap, stride * n_glyphs, "glyph pixels")
        index_bytes = _slice(block, map_at, 2 * n_map, "Unicode map")
        if any(block[map_at + 2 * n_map:metrics_at]):
            raise NetworkFontError("Nonzero PF map alignment padding")
        indices = struct.unpack(f"<{n_map}H", index_bytes)
        range_bytes = _slice(block, ranges_at, 16 * n_ranges, "Unicode ranges")
        metric_bytes = _slice(block, metrics_at, 16 * n_metrics, "metrics")
        ranges = tuple(PFRange(*row) for row in struct.iter_unpack("<4I", range_bytes))
        metrics = tuple(struct.iter_unpack("<8h", metric_bytes))
        palette_bytes = _slice(block, palette_at, 64, "palette")
        palette = tuple(tuple(palette_bytes[i:i + 4]) for i in range(0, 64, 4))
        if any(c[3] > 128 for c in palette) or not any(c[3] == 0 for c in palette) or not any(c[3] and max(c[:3]) for c in palette):
            raise NetworkFontError("Unsupported palette alpha/coverage")
        previous, expected_map = -1, 0
        for span in ranges:
            if (not previous < span.first <= span.last <= 0xFFFF or span.map_base != expected_map
                    or span.glyph_base >= n_glyphs):
                raise NetworkFontError("Invalid/overlapping Unicode range")
            expected_map += span.last - span.first + 1
            if expected_map > n_map:
                raise NetworkFontError("Unicode range exceeds index table")
            for code in range(span.first, span.last + 1):
                index = indices[span.map_base + code - span.first]
                if index == 0xFFFF:
                    continue
                index += span.glyph_base
                if index >= n_glyphs:
                    raise NetworkFontError("Unicode lookup exceeds glyph table")
                metric = metrics[index if header[4] & 8 else 0]
                if metric[6] < 0:
                    raise NetworkFontError("Negative glyph advance")
                glyph = PFGlyph(number, index, offset + bitmap + index * stride, stride, width, height, metric)
                if code in glyphs:
                    shadowed.append(code)
                else:
                    glyphs[code] = glyph
            previous = span.last
        if expected_map != n_map:
            raise NetworkFontError("Unaccounted Unicode index entries")
        blocks.append(PFSubfont(number, offset, size, header[4], width, height, asc, desc, max_advance, n_glyphs, stride, offset + bitmap, ranges, indices, metrics, palette))
    return PFFont(data, names[0], names[1], ascent, descent, advance, tuple(blocks), glyphs, tuple(shadowed))


def collect_protected_codepoints(elf: bytes) -> set[int]:
    """Read complete printable UTF-8 NUL strings in all ELF32 PT_LOAD spans.

    This is a bounded static survey, not proof against generated strings,
    external resources, non-NUL encodings or user-supplied network/save names.
    """
    if len(elf) < 52 or elf[:7] != b"\x7fELF\x01\x01\x01" or struct.unpack_from("<H", elf, 18)[0] != 8:
        raise NetworkFontError("Expected little-endian MIPS ELF32")
    phoff = struct.unpack_from("<I", elf, 28)[0]
    phsize, count = struct.unpack_from("<HH", elf, 42)
    if phsize != 32 or not count:
        raise NetworkFontError("Unsupported ELF program headers")
    table = _slice(elf, phoff, count * 32, "ELF program headers")
    result = set()
    for i in range(count):
        kind, offset, _, _, size, memory, _, _ = struct.unpack_from("<8I", table, i * 32)
        if kind != 1:
            continue
        if size > memory:
            raise NetworkFontError("ELF file span exceeds memory span")
        for raw in _slice(elf, offset, size, "ELF load segment").split(b"\0")[:-1]:
            try:
                value = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if value and all(c.isprintable() or c in "\r\n\t" for c in value):
                result.update(ord(c) for c in value if ord(c) >= 128)
    return result


def allocate_mapping(font: PFFont, texts: Iterable[str], *, protected_codepoints: Iterable[int]) -> dict[str, int]:
    """Use native glyphs unchanged; assign absent glyphs to unused Hangul slots."""
    texts = list(texts)
    if any(not isinstance(t, str) or "\0" in t for t in texts):
        raise NetworkFontError("Text must be strings without NUL")
    required = sorted({c for text in texts for c in text if ord(c) >= 128})
    if any(0xD800 <= ord(c) <= 0xDFFF or ord(c) > 0xFFFF for c in required):
        raise NetworkFontError("Only BMP Unicode scalar targets are supported")
    protected = set(protected_codepoints)
    if any(type(c) is not int or not 0 <= c <= 0x10FFFF for c in protected):
        raise NetworkFontError("Invalid protected Unicode codepoint")
    used = protected | {ord(c) for c in required}
    protected_pixels = {glyph.offset for code, glyph in font.glyphs.items() if code in used}
    candidates = []
    candidate_pixels = set()
    for code, glyph in sorted(font.glyphs.items()):
        block = font.subfonts[glyph.subfont]
        if (0xAC00 <= code <= 0xD7A3 and code not in used and block.flags == 0
                and glyph.offset not in protected_pixels and glyph.offset not in candidate_pixels
                and (glyph.width, glyph.height) == (26, 26)):
            candidates.append(code)
            candidate_pixels.add(glyph.offset)
    missing = [c for c in required if ord(c) not in font.glyphs]
    if len(missing) > len(candidates):
        raise NetworkFontError(f"Insufficient unprotected network glyphs: {len(missing)} > {len(candidates)}")
    assigned = dict(zip(missing, candidates))
    return {c: assigned.get(c, ord(c)) for c in required}


def _check_mapping(mapping: Mapping[str, int]) -> dict[int, str]:
    reverse = {}
    for char, code in mapping.items():
        if (not isinstance(char, str) or len(char) != 1 or ord(char) < 128
                or type(code) is not int or not 128 <= code <= 0xFFFF or 0xD800 <= code <= 0xDFFF
                or 0xD800 <= ord(char) <= 0xDFFF or ord(char) > 0xFFFF or code in reverse):
            raise NetworkFontError("Invalid or duplicate Unicode glyph mapping")
        reverse[code] = char
    return reverse


def encode_text(text: str, mapping: Mapping[str, int]) -> bytes:
    _check_mapping(mapping)
    if not isinstance(text, str) or "\0" in text:
        raise NetworkFontError("Text must not contain NUL")
    result = []
    for char in text:
        if ord(char) < 128:
            result.append(char)
        elif char in mapping:
            result.append(chr(mapping[char]))
        else:
            raise NetworkFontError(f"Missing network glyph assignment: {char!r}")
    return "".join(result).encode("utf-8")


def decode_text(data: bytes, mapping: Mapping[str, int]) -> str:
    reverse = _check_mapping(mapping)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise NetworkFontError("Invalid network UTF-8") from exc
    result = []
    for char in text:
        if char == "\0":
            raise NetworkFontError("Unexpected NUL in network text")
        if ord(char) < 128:
            result.append(char)
        elif ord(char) in reverse:
            result.append(reverse[ord(char)])
        else:
            raise NetworkFontError("Unmapped Unicode value in network text")
    return "".join(result)


def decode_glyph(font: PFFont, code: int):
    """Decode the actual 4-bpp cell; it is not a runtime layout emulation."""
    from PIL import Image
    glyph = font.glyphs.get(code)
    if glyph is None:
        raise NetworkFontError(f"Missing PF glyph: U+{code:04X}")
    raw = font.data[glyph.offset:glyph.offset + (glyph.width * glyph.height + 1) // 2]
    values = [n for byte in raw for n in (byte & 15, byte >> 4)]
    palette = font.subfonts[glyph.subfont].palette
    image = Image.new("RGBA", (glyph.width, glyph.height))
    image.putdata([palette[i][:3] + (min(255, palette[i][3] * 255 // 128),) for i in values[:glyph.width * glyph.height]])
    return image


def patch_glyph_masks(data: bytes, mapping: Mapping[str, int], masks: Mapping[str, object], *, protected_codepoints: Iterable[int]) -> bytes:
    """Overlay Pillow L masks in selected Hangul cells, with a black edge.

    Quantization uses the original palette's premultiplied color and alpha.
    Only packed image nibbles are touched, never alignment padding or metrics.
    """
    from PIL import ImageFilter
    font = parse_pf(data)
    _check_mapping(mapping)
    changed = {c: code for c, code in mapping.items() if code != ord(c)}
    if set(masks) != set(changed):
        raise NetworkFontError("Masks do not exactly match remapped glyphs")
    protected = set(protected_codepoints)
    if any(type(code) is not int or not 0 <= code <= 0x10FFFF for code in protected):
        raise NetworkFontError("Invalid protected Unicode codepoint")
    native = {code for char, code in mapping.items() if code == ord(char)}
    protected_pixels = {glyph.offset for code, glyph in font.glyphs.items() if code in protected | native}
    physical = set()
    planned = []
    for char, code in changed.items():
        glyph = font.glyphs.get(code)
        if (code in protected or not 0xAC00 <= code <= 0xD7A3 or glyph is None
                or ord(char) in font.glyphs or glyph.offset in protected_pixels
                or font.subfonts[glyph.subfont].flags != 0 or (glyph.width, glyph.height) != (26, 26)):
            raise NetworkFontError("Protected or unsupported PF destination")
        if glyph.offset in physical:
            raise NetworkFontError("Duplicate physical PF glyph")
        physical.add(glyph.offset)
        mask = masks[char]
        if getattr(mask, "mode", None) != "L" or getattr(mask, "size", None) != (glyph.width, glyph.height):
            raise NetworkFontError("Glyph mask mode/dimensions mismatch")
        if not mask.getbbox() and not char.isspace():
            raise NetworkFontError("Blank target glyph")
        fill = mask.tobytes()
        outline = mask.filter(ImageFilter.MaxFilter(3)).tobytes()
        palette = font.subfonts[glyph.subfont].palette
        premultiplied = [(r * a / 128, g * a / 128, b * a / 128, a * 255 / 128) for r, g, b, a in palette]
        # Quantize each observed coverage pair once. White fill is composited
        # over the black outline using the shipped palette's alpha ceiling.
        peak = max(c[3] for c in palette)
        black = max((c[3] for c in palette if not any(c[:3])), default=0)
        cache = {}
        packed = bytearray(data[glyph.offset:glyph.offset + (glyph.width * glyph.height + 1) // 2])
        for i, pair in enumerate(zip(fill, outline)):
            if pair not in cache:
                f, o = pair
                fa = peak / 128 * f / 255
                oa = black / 128 * o / 255
                color = (255 * fa,) * 3 + (255 * (fa + oa * (1 - fa)),)
                cache[pair] = min(range(16), key=lambda j: (sum((x - y) ** 2 for x, y in zip(color, premultiplied[j])), j))
            value = cache[pair]
            if i & 1:
                packed[i // 2] = (packed[i // 2] & 15) | value << 4
            else:
                packed[i // 2] = (packed[i // 2] & 240) | value
        planned.append((glyph.offset, bytes(packed)))
    output = bytearray(data)
    for offset, payload in planned:
        output[offset:offset + len(payload)] = payload
    return bytes(output)


def build_network_font(data: bytes, texts: Iterable[str], font_path: str | Path, expected_font_sha256: str, *, protected_codepoints: Iterable[int], expected_source_sha256: str = KOREAN_SHA256, pixel_size: int = 23) -> NetworkFontBuild:
    """Return an equal-sized hash-bound PF copy and its mandatory UTF-8 map."""
    from fontTools.ttLib import TTFont
    from PIL import Image, ImageDraw, ImageFont
    source_sha = hashlib.sha256(data).hexdigest()
    if source_sha != expected_source_sha256.lower():
        raise NetworkFontError("PF source SHA-256 mismatch")
    font_data = Path(font_path).read_bytes()
    font_sha = hashlib.sha256(font_data).hexdigest()
    if font_sha != expected_font_sha256.lower():
        raise NetworkFontError("Outline font SHA-256 mismatch")
    if type(pixel_size) is not int or not 1 <= pixel_size <= 24:
        raise NetworkFontError("Invalid PF outline pixel size")
    texts, protected = list(texts), set(protected_codepoints)
    font = parse_pf(data)
    mapping = allocate_mapping(font, texts, protected_codepoints=protected)
    aliased = {c: code for c, code in mapping.items() if code != ord(c)}
    with TTFont(io.BytesIO(font_data), lazy=True) as outline:
        cmap = outline.getBestCmap()
        missing = [c for c in aliased if ord(c) not in cmap]
        if missing:
            raise NetworkFontError(f"Outline font missing glyphs: {''.join(missing)}")
        ascent = outline["OS/2"].sTypoAscender / outline["head"].unitsPerEm
    scale = 4
    face = ImageFont.truetype(io.BytesIO(font_data), pixel_size * scale)
    masks = {}
    for char, code in aliased.items():
        glyph = font.glyphs[code]
        width, height = glyph.width * scale, glyph.height * scale
        baseline = round(pixel_size * scale * ascent + (height - pixel_size * scale) / 2)
        x = round((width - face.getlength(char)) / 2)
        left, top, right, bottom = face.getbbox(char, anchor="ls")
        if x + left < scale or x + right > width - scale or baseline + top < scale or baseline + bottom > height - scale:
            raise NetworkFontError(f"Outline exceeds PF cell with edge padding: {char!r}")
        image = Image.new("L", (width, height))
        ImageDraw.Draw(image).text((x, baseline), char, font=face, fill=255, anchor="ls")
        masks[char] = image.resize((glyph.width, glyph.height), Image.Resampling.LANCZOS)
    output = patch_glyph_masks(data, mapping, masks, protected_codepoints=protected)
    reparsed = parse_pf(output)
    if len(output) != len(data) or reparsed.subfonts != font.subfonts or reparsed.glyphs != font.glyphs:
        raise NetworkFontError("PF structure changed during glyph overlay")
    edits = []
    allowed = []
    for char, code in aliased.items():
        glyph = font.glyphs[code]
        size = (glyph.width * glyph.height + 1) // 2
        before, after = data[glyph.offset:glyph.offset + size], output[glyph.offset:glyph.offset + size]
        if before == after and not char.isspace():
            raise NetworkFontError("Target glyph did not change")
        edits.append({"character": char, "unicode_slot": code, "offset": glyph.offset, "size": size,
                      "before_sha256": hashlib.sha256(before).hexdigest(), "after_sha256": hashlib.sha256(after).hexdigest()})
        allowed.append((glyph.offset, glyph.offset + size))
    end = 0
    for first, last in sorted(allowed):
        if first < end or data[end:first] != output[end:first]:
            raise NetworkFontError("Unexpected PF change outside intended glyphs")
        end = last
    if data[end:] != output[end:]:
        raise NetworkFontError("Unexpected PF trailing change")
    for text in texts:
        if decode_text(encode_text(text, mapping), mapping) != text:
            raise NetworkFontError("Network UTF-8 mapping round trip failed")
    return NetworkFontBuild(output, mapping, tuple(edits), source_sha, font_sha, pixel_size)


def render_preview(data: bytes, text: str, mapping: Mapping[str, int], *, scale: int = 3):
    """Render rebuilt PF cells on a fixed grid, explicitly not UI-layout proof."""
    from PIL import Image
    if type(scale) is not int or not 1 <= scale <= 8:
        raise NetworkFontError("Invalid preview scale")
    font = parse_pf(data)
    encoded = encode_text(text, mapping).decode("utf-8")
    lines = encoded.split("\n")
    result = Image.new("RGBA", (max(1, max(map(len, lines))) * 26, max(1, len(lines)) * 30))
    for y, line in enumerate(lines):
        for x, char in enumerate(line):
            if char == " ":
                continue
            cell = decode_glyph(font, ord(char))
            result.alpha_composite(cell, (x * 26, y * 30))
    return result.resize((result.width * scale, result.height * scale), Image.Resampling.NEAREST)
