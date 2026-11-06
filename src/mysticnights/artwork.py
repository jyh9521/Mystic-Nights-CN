"""Source-locked, reversible pixel deltas for authored localized artwork.

Only changed palette indices are distributed. Original artwork, atlas metadata
and CLUTs come from the user's verified disc, not from complete checked-in images.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def import_indexed_pixels(source: bytes, artwork, rectangles: list, *, source_sha256: str,
                          reference: bytes | None = None, reference_sha256: str | None = None,
                          reference_rectangles: list | None = None,
                          palette_constraints: list | None = None) -> bytes:
    """Import reviewed RGBA artwork without typesetting or regenerating a CLUT.

    Unchanged decoded pixels retain their original *index*, even when the
    palette contains duplicate colors. Quantization compares premultiplied
    RGB and alpha, avoiding opaque fringes around transparent lettering.
    A hash-bound, same-header/CLUT reference may retain already-localized
    equal-color indices inside allowed regions. It cannot introduce colors,
    change quantized RGBA, or expand the permitted edit area.
    """
    from .graphics import decode_tim2, _palette

    if digest(source) != source_sha256:
        raise ValueError("Artwork import source identity mismatch")
    original, info = decode_tim2(source)
    if info["image_type"] != 5 or artwork.mode != "RGBA" or artwork.size != original.size:
        raise ValueError("Artwork import requires matching indexed TIM2 and RGBA dimensions")
    allowed = validate_rectangles(rectangles, *original.size)
    colors = _palette(source, info)
    # A material may require uniform opacity even if old glyphs used slightly
    # different CLUT alpha. Restrict candidates, never regenerate the palette.
    constrained = {}
    if palette_constraints is not None:
        if not isinstance(palette_constraints, list):
            raise ValueError('Invalid artwork palette constraints')
        for rule in palette_constraints:
            region = validate_rectangles([rule['rect']], *original.size)
            if not region <= allowed or region & constrained.keys():
                raise ValueError('Palette constraint overlaps or exceeds allowed pixels')
            low, high = rule['min_alpha'], rule['max_alpha']
            if type(low) is not int or type(high) is not int or not 0 <= low <= high <= 255:
                raise ValueError('Invalid palette alpha range')
            candidates = tuple(n for n, c in enumerate(colors) if low <= c[3] <= high)
            if not candidates:
                raise ValueError('No palette colors in requested alpha range')
            constrained.update((i, candidates) for i in region)
    if reference is not None:
        if reference_sha256 is None or digest(reference) != reference_sha256:
            raise ValueError("Artwork reference identity mismatch")
        if (len(reference) != len(source)
                or reference[:info["pixel_offset"]] != source[:info["pixel_offset"]]
                or reference[info["palette_offset"]:] != source[info["palette_offset"]:]):
            raise ValueError("Artwork reference header/palette mismatch")
    elif reference_sha256 is not None:
        raise ValueError("Artwork reference bytes missing")
    preferred = allowed if reference_rectangles is None else validate_rectangles(reference_rectangles, *original.size)
    if not preferred <= allowed:
        raise ValueError("Artwork reference regions exceed allowed pixels")
    if reference is None and reference_rectangles is not None:
        raise ValueError("Artwork reference regions require reference bytes")

    def premultiply(color):
        return tuple(color[k] * color[3] // 255 for k in range(3)) + (color[3],)

    palette = [premultiply(c) for c in colors]
    unrestricted = tuple(range(len(palette)))
    output = bytearray(source)
    cache = {}
    for i, (before, after) in enumerate(zip(original.get_flattened_data(), artwork.get_flattened_data())):
        candidates = constrained.get(i, unrestricted)
        original_index = source[info['pixel_offset'] + i]
        if before == after and original_index in candidates:
            continue
        if i not in allowed:
            raise ValueError(f"Artwork import changed protected pixel ({i % original.width}, {i // original.width})")
        if premultiply(before) == premultiply(after) and original_index in candidates:
            continue
        cache_key = (after, candidates)
        if cache_key not in cache:
            value = premultiply(after)
            cache[cache_key] = min(candidates, key=lambda n:
                sum((palette[n][k] - value[k]) ** 2 * (2 if k == 3 else 1) for k in range(4)))
        output[info["pixel_offset"] + i] = cache[cache_key]
    if reference is not None:
        start = info["pixel_offset"]
        for i in preferred:
            old_index = reference[start + i]
            if colors[old_index] == colors[output[start + i]]:
                output[start + i] = old_index
    return bytes(output)


def load_graphics_catalogue(path: Path) -> dict:
    catalogue = json.loads(path.read_text(encoding="utf8"))
    patches = []
    seen = set()
    for name in catalogue.get("artwork_files", []):
        if not isinstance(name, str):
            raise ValueError("Invalid authored artwork path")
        rel = PurePosixPath(name)
        if (not isinstance(name, str) or "\\" in name or rel.is_absolute()
                or ":" in name or ".." in rel.parts or rel.suffix != ".json"
                or len(rel.parts) != 2 or rel.parts[0] != "artwork" or name in seen):
            raise ValueError("Invalid authored artwork path")
        seen.add(name)
        target = (path.parent / name).resolve()
        if target.parent != (path.parent / "artwork").resolve():
            raise ValueError("Authored artwork escaped locale directory")
        patches.append(json.loads(target.read_text(encoding="utf8")))
    if "artwork_patches" in catalogue:
        raise ValueError("Use artwork_files in editable catalogues")
    catalogue["artwork_patches"] = patches
    return catalogue


def _byte_list(values):
    if not isinstance(values, list) or not values or any(type(v) is not int or not 0 <= v <= 255 for v in values):
        raise ValueError("Invalid artwork byte list")
    return bytes(values)


def validate_rectangles(rectangles, width, height):
    allowed = set()
    for rect in rectangles:
        if not isinstance(rect, list) or len(rect) != 4 or any(type(v) is not int for v in rect):
            raise ValueError("Invalid authored artwork rectangle")
        x, y, w, h = rect
        if x < 0 or y < 0 or w < 1 or h < 1 or x + w > width or y + h > height:
            raise ValueError("Authored artwork rectangle outside pixels")
        allowed.update(yy * width + xx for yy in range(y, y + h) for xx in range(x, x + w))
    return allowed


def apply_artwork(data: bytes, patch: dict, *, targets: dict | None = None, reverse=False) -> bytes:
    from .graphics import decode_tim2
    if patch.get("format") != "indexed-artwork-delta" or patch.get("version") != 1:
        raise ValueError("Unsupported authored artwork delta")
    before_key, after_key = ("modified_sha256", "source_sha256") if reverse else ("source_sha256", "modified_sha256")
    if len(data) != patch["size"] or digest(data) != patch[before_key]:
        raise ValueError("Authored artwork source identity mismatch")
    if targets is not None and targets != patch["targets"]:
        raise ValueError("Authored artwork text changed; redraw required")
    _, info = decode_tim2(data)
    if [info[k] for k in ("width", "height", "image_type", "clut_type")] != patch["profile"] or info["image_type"] != 5:
        raise ValueError("Authored artwork profile mismatch")
    allowed = validate_rectangles(patch["allowed_rectangles"], info["width"], info["height"])
    if not patch.get("ranges"):
        raise ValueError("Authored artwork delta is empty")
    start = info["pixel_offset"]
    output = bytearray(data)
    end = 0
    for span in patch["ranges"]:
        offset = span["pixel_offset"]
        before, after = _byte_list(span["before"]), _byte_list(span["after"])
        if reverse:
            before, after = after, before
        if (type(offset) is not int or offset < end or len(before) != len(after)
                or not set(range(offset, offset + len(before))) <= allowed):
            raise ValueError("Invalid/overlapping/unapproved artwork pixel range")
        if data[start + offset:start + offset + len(before)] != before:
            raise ValueError("Authored artwork expected pixels changed")
        output[start + offset:start + offset + len(after)] = after
        end = offset + len(after)
    if digest(output) != patch[after_key]:
        raise ValueError("Authored artwork output identity mismatch")
    if not reverse and "state_checks" in patch:
        from .artwork_checks import check_state_pairs
        rendered, _ = decode_tim2(bytes(output))
        check_state_pairs(rendered, patch["state_checks"])
    if not reverse and "clear_regions" in patch:
        from .artwork_checks import check_clear_regions
        rendered, _ = decode_tim2(bytes(output))
        check_clear_regions(rendered, patch["clear_regions"])
    if not reverse and "size_groups" in patch:
        from .artwork_checks import check_size_groups
        rendered, _ = decode_tim2(bytes(output))
        check_size_groups(rendered, patch["size_groups"])
    if not reverse and "shape_pairs" in patch:
        from .artwork_checks import check_shape_pairs
        rendered, _ = decode_tim2(bytes(output))
        check_shape_pairs(rendered, patch["shape_pairs"])
    if not reverse and "anchor_gap_groups" in patch:
        from .artwork_checks import check_anchor_gaps
        rendered, _ = decode_tim2(bytes(output))
        check_anchor_gaps(rendered, patch["anchor_gap_groups"])
    return bytes(output)


def make_artwork_delta(before: bytes, after: bytes, rectangles: list, targets: dict) -> dict:
    from .graphics import decode_tim2
    _, info = decode_tim2(before)
    _, other = decode_tim2(after)
    if (info != other or len(before) != len(after)
            or before[:info["pixel_offset"]] != after[:info["pixel_offset"]]
            or before[info["palette_offset"]:] != after[info["palette_offset"]:]):
        raise ValueError("Authored artwork changed atlas structure or palette")
    allowed = validate_rectangles(rectangles, info["width"], info["height"])
    start = info["pixel_offset"]
    old, new = before[start:info["palette_offset"]], after[start:info["palette_offset"]]
    spans = []
    i = 0
    while i < len(old):
        if old[i] == new[i]:
            i += 1
            continue
        first = i
        while i < len(old) and old[i] != new[i]:
            if i not in allowed:
                raise ValueError(f"Artwork altered protected pixel ({i % info['width']}, {i // info['width']})")
            i += 1
        spans.append({"pixel_offset": first, "before": list(old[first:i]), "after": list(new[first:i])})
    patch = {"format": "indexed-artwork-delta", "version": 1, "size": len(before),
             "source_sha256": digest(before), "modified_sha256": digest(after),
             "profile": [info[k] for k in ("width", "height", "image_type", "clut_type")],
             "targets": targets, "allowed_rectangles": rectangles, "ranges": spans}
    if apply_artwork(before, patch, targets=targets) != after or apply_artwork(after, patch, reverse=True) != before:
        raise AssertionError("Artwork delta round trip failed")
    return patch
