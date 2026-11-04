"""Version-locked, palette-preserving edits of explicitly reviewed text rectangles.

The engine receives original TIM2 dimensions, metadata and palettes.  Source
bytes and every text rectangle are locked by hashes.  Only approved uniform
background rectangles are writable; complex artwork stays separately pending.
"""
from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
import struct
from typing import Mapping

from .resources import parse_res


def decode_tim2(data: bytes):
    """Return Pillow RGBA image and validated profile metadata; reject others."""
    from PIL import Image

    if len(data) < 64 or data[:8] != b"TIM2\x04\x00\x01\x00":
        raise ValueError("unsupported TIM2 version/layout/picture count")
    total, palette_size, pixel_size = struct.unpack_from("<III", data, 16)
    header_size, palette_count = struct.unpack_from("<HH", data, 28)
    picture_format, mipmaps, clut_type, image_type = data[32:36]
    width, height = struct.unpack_from("<HH", data, 36)
    if (header_size != 48 or picture_format != 0 or mipmaps != 1
            or not width or not height or width > 2048 or height > 2048):
        raise ValueError("unsupported picture header/dimensions")
    if total != header_size + pixel_size + palette_size or len(data) != 16 + total:
        raise ValueError("TIM2 picture/file lengths disagree")
    pixel_start = 16 + header_size
    palette_start = pixel_start + pixel_size
    if image_type == 3 and clut_type == 0:
        if palette_count or palette_size or pixel_size != width * height * 4:
            raise ValueError("invalid RGBA32 profile lengths")
        rgba = bytearray(data[pixel_start:palette_start])
        for offset in range(3, len(rgba), 4):
            rgba[offset] = min(255, rgba[offset] * 255 // 128)
        image = Image.frombytes("RGBA", (width, height), bytes(rgba))
    elif image_type == 5 and clut_type in (1, 3):
        stride = 2 if clut_type == 1 else 4
        if (palette_count != 256 or palette_size != 256 * stride
                or pixel_size != width * height):
            raise ValueError("invalid indexed profile lengths")
        colors = []
        for index in range(256):
            physical = ((index & ~0x18) | ((index & 8) << 1)
                        | ((index & 16) >> 1))
            offset = palette_start + physical * stride
            if stride == 4:
                r, g, b, a = data[offset:offset + 4]
                colors.append((r, g, b, min(255, a * 255 // 128)))
            else:
                value, = struct.unpack_from("<H", data, offset)
                colors.append(tuple(((value >> shift) & 31) * 255 // 31
                                    for shift in (0, 5, 10))
                              + (255 if value & 0x8000 else 0,))
        indexed = Image.frombytes("P", (width, height), data[pixel_start:palette_start])
        indexed.putpalette(bytes(channel for color in colors for channel in color), "RGBA")
        image = indexed.convert("RGBA")
    else:
        raise ValueError(f"unsupported image/clut types {image_type}/{clut_type}")
    return image, {
        "width": width, "height": height, "image_type": image_type,
        "clut_type": clut_type, "pixel_offset": pixel_start,
        "pixel_size": pixel_size, "palette_offset": palette_start,
        "palette_size": palette_size, "pixel_layout": "linear",
    }


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _rect_bytes(data: bytes, info: dict, rect: list[int]) -> bytes:
    if not isinstance(rect, (list, tuple)) or len(rect) != 4:
        raise ValueError("text rectangle requires four integer coordinates")
    x, y, width, height = rect
    if (any(type(v) is not int for v in rect) or x < 0 or y < 0
            or width < 1 or height < 1 or x + width > info["width"]
            or y + height > info["height"]):
        raise ValueError("text rectangle is outside the original texture")
    start = info["pixel_offset"]
    stride = info["width"]
    return b"".join(data[start + row * stride + x:start + row * stride + x + width]
                    for row in range(y, y + height))


def _palette(data: bytes, info: dict) -> list[tuple[int, int, int, int]]:
    if info["image_type"] != 5 or info["clut_type"] not in (1, 3):
        raise ValueError("only reviewed 8-bit indexed textures are writable")
    colors = []
    stride = 2 if info["clut_type"] == 1 else 4
    for index in range(256):
        physical = (index & ~0x18) | ((index & 8) << 1) | ((index & 16) >> 1)
        offset = info["palette_offset"] + physical * stride
        if stride == 4:
            r, g, b, a = data[offset:offset + 4]
            colors.append((r, g, b, min(255, a * 255 // 128)))
        else:
            value, = struct.unpack_from("<H", data, offset)
            colors.append(tuple(((value >> shift) & 31) * 255 // 31
                                for shift in (0, 5, 10))
                          + (255 if value & 0x8000 else 0,))
    return colors


def _visible(color: tuple[int, ...]) -> tuple[int, ...]:
    return (0, 0, 0, 0) if color[3] == 0 else color


def patch_texture(data: bytes, recipe: dict, targets: Mapping[str, str], font_source: Path | bytes) -> bytes:
    """Plan and validate all slots before returning an equal-size modified copy.

    Coordinates are [x, y, width, height] in the original texture.  Fill is only
    accepted when the reviewed rectangle has a uniform source-color perimeter.
    The recipe still requires visual review: a flat perimeter alone does not
    prove absence of artwork inside a rectangle.
    """
    from PIL import Image, ImageDraw, ImageFont
    from fontTools.ttLib import TTFont

    if _sha(data) != recipe["sha256"]:
        raise ValueError("texture source hash mismatch")
    _, info = decode_tim2(data)
    if (info["width"], info["height"], info["image_type"], info["clut_type"]) != tuple(recipe["profile"]):
        raise ValueError("texture profile mismatch")
    colors = _palette(data, info)
    # Distances in straight-alpha RGB make nearly transparent coverage select
    # an opaque bright palette entry.  Compare premultiplied visible colors.
    premultiplied = [tuple(c[i] * c[3] // 255 for i in range(3)) + (c[3],)
                     for c in colors]
    slots = {slot["id"]: slot for slot in recipe["slots"] if slot.get("install")}
    if len(slots) != sum(bool(slot.get("install")) for slot in recipe["slots"]):
        raise ValueError("duplicate graphics slot ID")
    if set(targets) - set(slots):
        raise ValueError("unknown or pending graphics target")
    font_bytes = font_source if isinstance(font_source, bytes) else font_source.read_bytes()
    font_file = TTFont(BytesIO(font_bytes), lazy=True)
    try:
        covered = set(font_file.getBestCmap())
    finally:
        font_file.close()
    planned = []
    occupied = set()
    for identifier, target in targets.items():
        slot = slots[identifier]
        if not target.strip() or "\0" in target or any(ord(c) not in covered for c in target if c != "\n"):
            raise ValueError(f"empty/NUL/unsupported graphics text: {identifier}")
        rect = slot["rect"]
        source = _rect_bytes(data, info, rect)
        if _sha(source) != slot["source_pixels_sha256"]:
            raise ValueError(f"graphics rectangle source mismatch: {identifier}")
        x, y, width, height = rect
        coordinates = {(xx, yy) for yy in range(y, y + height) for xx in range(x, x + width)}
        if coordinates & occupied:
            raise ValueError(f"overlapping graphics rectangles: {identifier}")
        occupied.update(coordinates)
        background = slot["background_index"]
        if type(background) is not int or not 0 <= background < 256:
            raise ValueError("invalid palette background index")
        # A separately reviewed all-text layer may already be clipped at the
        # texture edge.  Internal boundaries must still be uniform; this is
        # never inferred merely from an alpha channel or resource name.
        clipped = slot.get("allow_texture_edge_clipping", False)
        edges = (source[:width] if not clipped or y else b"")
        edges += source[-width:] if not clipped or y + height != info["height"] else b""
        edges += source[::width] if not clipped or x else b""
        edges += source[width - 1::width] if not clipped or x + width != info["width"] else b""
        if not edges:
            raise ValueError("graphics rectangle has no interior background boundary")
        mode = slot.get("background_mode", "uniform")
        if mode not in ("uniform", "reviewed-solid-panel"):
            raise ValueError("unsupported graphics background reconstruction")
        if mode == "reviewed-solid-panel" and not slot.get("review_note", "").strip():
            raise ValueError("graphics panel requires an explicit artwork review")
        if mode == "uniform" and any(_visible(colors[p]) != _visible(colors[background]) for p in edges):
            raise ValueError(f"nonuniform graphics perimeter requires art restoration: {identifier}")
        foreground = tuple(slot["foreground_rgba"])
        if len(foreground) != 4 or any(type(c) is not int or not 0 <= c <= 255 for c in foreground):
            raise ValueError("invalid foreground color")
        if (type(slot["font_size"]) is not int or type(slot["minimum_font_size"]) is not int
                or not 1 <= slot["minimum_font_size"] <= slot["font_size"] <= 512):
            raise ValueError("invalid graphics font size range")
        angle = slot.get("rotation_degrees", 0)
        if type(angle) is not int or not -180 <= angle <= 180:
            raise ValueError("invalid graphics text rotation")
        render_width, render_height = (height, width) if abs(angle) == 90 else (width, height)
        scale = 4
        mask = Image.new("L", (render_width * scale, render_height * scale), 0)
        draw = ImageDraw.Draw(mask)
        fitted = None
        for size in range(slot["font_size"], slot["minimum_font_size"] - 1, -1):
            font = ImageFont.truetype(BytesIO(font_bytes), size * scale)
            box = draw.multiline_textbbox((0, 0), target, font=font, spacing=2 * scale, align="center")
            if box[2] - box[0] <= (render_width - 2) * scale and box[3] - box[1] <= (render_height - 2) * scale:
                fitted = font, box
                break
        if fitted is None:
            raise ValueError(f"graphics text does not fit reviewed rectangle: {identifier}")
        font, box = fitted
        tx = (render_width * scale - box[2] + box[0]) // 2 - box[0]
        ty = (render_height * scale - box[3] + box[1]) // 2 - box[1]
        draw.multiline_text((tx, ty), target, font=font, fill=255, spacing=2 * scale, align="center")
        mask = mask.resize((render_width, render_height), Image.Resampling.LANCZOS)
        if angle:
            mask = mask.rotate(angle, Image.Resampling.BICUBIC, expand=abs(angle) == 90)
        if mask.size != (width, height):
            raise AssertionError("graphics text rotation changed rectangle size")
        preserved = set()
        if "erase_polygon" in slot:
            polygon = slot["erase_polygon"]
            if (mode != "reviewed-solid-panel" or len(polygon) < 3
                    or any(len(point) != 2 or any(type(v) is not int for v in point)
                           or not x <= point[0] < x + width or not y <= point[1] < y + height
                           for point in polygon)):
                raise ValueError("invalid reviewed graphics erase polygon")
            allowed_mask = Image.new("1", (width, height), 0)
            ImageDraw.Draw(allowed_mask).polygon([(px - x, py - y) for px, py in polygon], fill=1)
            preserved.update(p for p, allowed in enumerate(allowed_mask.get_flattened_data()) if not allowed)
        for protected in slot.get("preserve_rects", []):
            px, py, pw, ph = protected
            if (any(type(v) is not int for v in protected) or pw < 1 or ph < 1
                    or px < x or py < y or px + pw > x + width or py + ph > y + height):
                raise ValueError("protected artwork rectangle is outside its text rectangle")
            preserved.update((yy - y) * width + xx - x
                             for yy in range(py, py + ph) for xx in range(px, px + pw))
        bg = colors[background]
        lookup = {0: background}
        pixels = bytearray()
        for pixel, coverage in enumerate(mask.get_flattened_data()):
            if pixel in preserved:
                if coverage > 1:
                    raise ValueError(f"graphics text overlaps protected artwork: {identifier}")
                pixels.append(source[pixel])
                continue
            if coverage not in lookup:
                if bg[3] == 0:
                    color = foreground[:3] + (foreground[3] * coverage // 255,)
                else:
                    color = tuple((bg[c] * (255 - coverage) + foreground[c] * coverage) // 255 for c in range(4))
                visible = tuple(color[i] * color[3] // 255 for i in range(3)) + (color[3],)
                lookup[coverage] = min(range(256), key=lambda p: sum((premultiplied[p][c] - visible[c]) ** 2
                                         * (2 if c == 3 else 1) for c in range(4)))
            pixels.append(lookup[coverage])
        planned.append((rect, bytes(pixels)))
    output = bytearray(data)
    for (x, y, width, height), pixels in planned:
        for row in range(height):
            offset = info["pixel_offset"] + (y + row) * info["width"] + x
            output[offset:offset + width] = pixels[row * width:(row + 1) * width]
    if len(output) != len(data) or output[:info["pixel_offset"]] != data[:info["pixel_offset"]] or output[info["palette_offset"]:] != data[info["palette_offset"]:]:
        raise AssertionError("graphics edit changed texture structure or palette")
    return bytes(output)


def build_graphics(image, manifest: dict, locale: dict, font_path: Path,
                   replacements: Mapping[str, bytes] | None = None) -> tuple[dict[str, bytes], dict]:
    """Compose reviewed texture changes with earlier equal-size RES changes.

    Original resources are hash-checked through ``image``.  Earlier changes may
    affect non-texture fields, but every selected texture must still have its
    original hash.  No filesystem writes, ISO mutation or runtime execution.
    """
    if manifest.get("format") != "graphics-text-slots" or manifest.get("version") != 1:
        raise ValueError("unsupported graphics manifest")
    if (locale.get("format") != "graphics-translations" or locale.get("version") != 1
            or not isinstance(locale.get("locale"), str) or not locale["locale"].strip()):
        raise ValueError("unsupported graphics locale")
    font_bytes = font_path.read_bytes()
    if _sha(font_bytes) != locale["font_sha256"]:
        raise ValueError("graphics font hash mismatch")
    from fontTools.ttLib import TTFont
    font_file = TTFont(BytesIO(font_bytes), lazy=True)
    try:
        covered = set(font_file.getBestCmap())
    finally:
        font_file.close()
    translations = {x["id"]: x for x in locale["entries"]}
    all_slots = [slot for texture in manifest["textures"] for slot in texture["slots"]]
    if len(translations) != len(locale["entries"]) or len({x["id"] for x in all_slots}) != len(all_slots):
        raise ValueError("duplicate graphics IDs")
    if set(translations) != {x["id"] for x in all_slots}:
        raise ValueError("graphics translation coverage mismatch")
    physical = set()
    for texture in manifest["textures"]:
        for ref in texture["references"]:
            key = (ref["resource"], ref["member"])
            if key in physical:
                raise ValueError("duplicate physical graphics member")
            physical.add(key)
    artwork = {r["source_sha256"]: r for r in locale.get("artwork_patches", [])}
    if len(artwork) != len(locale.get("artwork_patches", [])):
        raise ValueError("duplicate authored artwork source")
    used_artwork = set()
    changes = {}
    originals = {}
    installed = []
    pending = []
    retained = []
    for texture in manifest["textures"]:
        targets = {}
        for slot in texture["slots"]:
            row = translations[slot["id"]]
            if (row["status"] not in ("draft", "reviewed") or not row["target"].strip()
                    or "\0" in row["target"] or any(ord(c) not in covered for c in row["target"] if c != "\n")):
                raise ValueError("graphics translation is unfinished")
            if slot.get("disposition") == "retain-identifier":
                if slot.get("install") or row["target"] != slot["source"]:
                    raise ValueError("retained graphics identifier must remain unchanged")
                retained.append(slot["id"])
            elif slot.get("install"):
                targets[slot["id"]] = row["target"]
            else:
                pending.append(slot["id"])
        if not targets:
            continue
        if not texture["references"]:
            raise ValueError("graphics texture has no source resource reference")
        source_texture = None
        for ref in texture["references"]:
            resource = ref["resource"]
            if resource not in originals:
                originals[resource] = image.read(resource)
            original = originals[resource]
            if _sha(original) != ref["resource_sha256"]:
                raise ValueError("graphics resource source hash mismatch")
            original_archive = parse_res(original)
            original_member = original_archive.get(ref["member"])
            if original_member.offset != ref["offset"] or original_member.size != ref["size"]:
                raise ValueError("graphics resource member moved")
            payload = original_archive.read(original_member)
            if _sha(payload) != texture["sha256"]:
                raise ValueError("graphics texture source hash mismatch")
            source_texture = payload
        if texture.get("rendering") == "authored-delta":
            from .artwork import apply_artwork
            if texture["sha256"] not in artwork:
                raise ValueError("missing authored artwork delta")
            patch = artwork[texture["sha256"]]
            if patch["allowed_rectangles"] != texture["artwork_rectangles"]:
                raise ValueError("authored artwork allowed rectangles changed")
            patched = apply_artwork(source_texture, patch, targets=targets)
            used_artwork.add(texture["sha256"])
        else:
            if manifest.get("art_direction") == "source-style-only":
                raise ValueError("source-style artwork requires authored deltas")
            patched = patch_texture(source_texture, texture, targets, font_bytes)
        for ref in texture["references"]:
            changes.setdefault(ref["resource"], {})[ref["member"]] = patched
        installed.extend(targets)
    if used_artwork != set(artwork):
        raise ValueError("unused authored artwork delta")
    output = dict(replacements or {})
    for resource, members in changes.items():
        original_archive = parse_res(originals[resource])
        archive = parse_res(output.get(resource, originals[resource]))
        if archive.entries != original_archive.entries:
            raise ValueError("earlier patch changed RES structure")
        for name in members:
            if archive.read(name) != original_archive.read(name):
                raise ValueError("earlier patch already changed a graphics target")
        output[resource] = archive.replace(members)
    return output, {"installed_slots": installed, "pending_art_restoration_slots": pending,
                    "retained_identifier_slots": retained,
                    "changed_resources": sorted(changes),
                    "changed_texture_members": sum(len(x) for x in changes.values())}
