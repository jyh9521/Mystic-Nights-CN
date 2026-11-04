"""Source-locked RGB24 artwork deltas, independent of locale and ISO layout."""
from .artwork import digest, validate_rectangles, _byte_list


def _profile(profile):
    if (not isinstance(profile, list) or len(profile) != 3
            or any(type(n) is not int or n < 1 for n in profile) or profile[2] != 3):
        raise ValueError("Invalid raw RGB24 profile")
    return profile[0], profile[1]


def apply_raw_delta(data: bytes, patch: dict, *, targets=None, reverse=False) -> bytes:
    if patch.get("format") != "rgb24-artwork-delta" or patch.get("version") != 1:
        raise ValueError("Unsupported raw artwork delta")
    width, height = _profile(patch["profile"])
    before_key, after_key = (("modified_sha256", "source_sha256") if reverse
                             else ("source_sha256", "modified_sha256"))
    if len(data) != width * height * 3 or len(data) != patch["size"] or digest(data) != patch[before_key]:
        raise ValueError("Raw artwork source identity mismatch")
    if targets is not None and targets != patch["targets"]:
        raise ValueError("Raw artwork text changed; redraw required")
    pixels = validate_rectangles(patch["allowed_rectangles"], width, height)
    if not patch.get("ranges"):
        raise ValueError("Raw artwork delta is empty")
    output = bytearray(data)
    end = 0
    for span in patch["ranges"]:
        offset = span["byte_offset"]
        before, after = _byte_list(span["before"]), _byte_list(span["after"])
        if reverse:
            before, after = after, before
        if (type(offset) is not int or offset < end or len(before) != len(after)
                or any(i // 3 not in pixels for i in range(offset, offset + len(before)))):
            raise ValueError("Invalid/overlapping/unapproved raw artwork range")
        if data[offset:offset + len(before)] != before:
            raise ValueError("Raw artwork expected bytes changed")
        output[offset:offset + len(after)] = after
        end = offset + len(after)
    if digest(output) != patch[after_key]:
        raise ValueError("Raw artwork output identity mismatch")
    return bytes(output)


def make_raw_delta(before: bytes, after: bytes, profile: list, rectangles: list, targets: dict) -> dict:
    width, height = _profile(profile)
    if len(before) != len(after) or len(before) != width * height * 3:
        raise ValueError("Raw artwork size mismatch")
    allowed = validate_rectangles(rectangles, width, height)
    spans = []
    for i, (old, new) in enumerate(zip(before, after)):
        if old == new:
            continue
        if i // 3 not in allowed:
            raise ValueError("Raw artwork changed protected pixel")
        if spans and spans[-1]["byte_offset"] + len(spans[-1]["before"]) == i:
            spans[-1]["before"].append(old); spans[-1]["after"].append(new)
        else:
            spans.append({"byte_offset": i, "before": [old], "after": [new]})
    patch = {"format": "rgb24-artwork-delta", "version": 1, "size": len(before),
             "profile": profile, "source_sha256": digest(before), "modified_sha256": digest(after),
             "allowed_rectangles": rectangles, "targets": targets, "ranges": spans}
    if apply_raw_delta(before, patch) != after or apply_raw_delta(after, patch, reverse=True) != before:
        raise ValueError("Raw artwork round trip failed")
    return patch


def validate_raw_images(recipe: dict, catalogue: dict) -> dict:
    if (recipe.get("format") != "raw-image-slots" or recipe.get("version") != 1
            or catalogue.get("format") != "raw-image-translations" or catalogue.get("version") != 1):
        raise ValueError("Unsupported raw image catalogue")
    images = recipe["images"]
    if len({r["resource"] for r in images}) != len(images):
        raise ValueError("Duplicate raw image resource")
    slots = [s for r in images for s in r["slots"]]
    entries = catalogue["entries"]
    targets = {r["id"]: r["target"] for r in entries}
    if (len(targets) != len(entries) or len({s["id"] for s in slots}) != len(slots)
            or set(targets) != {s["id"] for s in slots}
            or any(r.get("status") not in ("draft", "reviewed") or not r["target"].strip()
                   or "\0" in r["target"] for r in entries)):
        raise ValueError("Raw image translation coverage mismatch")
    patches = {r["source_sha256"]: r for r in catalogue.get("artwork_patches", [])}
    if len(patches) != len(catalogue.get("artwork_patches", [])) or set(patches) != {r["sha256"] for r in images}:
        raise ValueError("Raw image artwork coverage mismatch")
    for r in images:
        width, height = _profile(r["profile"])
        patch = patches[r["sha256"]]
        rects = [s["rect"] for s in r["slots"]]
        validate_rectangles(rects, width, height)
        if (patch["profile"] != r["profile"] or patch["size"] != width * height * 3
                or patch["allowed_rectangles"] != rects
                or patch["targets"] != {s["id"]: targets[s["id"]] for s in r["slots"]}):
            raise ValueError("Raw image artwork binding mismatch")
    return {"installed_slots": [s["id"] for s in slots], "changed_resources": [r["resource"] for r in images]}


def build_raw_images(image, recipe: dict, catalogue: dict, replacements=None):
    report = validate_raw_images(recipe, catalogue)
    patches = {r["source_sha256"]: r for r in catalogue["artwork_patches"]}
    output = dict(replacements or {})
    for row in recipe["images"]:
        resource = row["resource"]
        source = image.read(resource)
        if resource in output and output[resource] != source:
            raise ValueError("Earlier patch already changed raw image target")
        output[resource] = apply_raw_delta(source, patches[row["sha256"]])
    return output, report
