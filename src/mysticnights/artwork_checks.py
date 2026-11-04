"""Data-driven pixel checks for paired states of authored indexed artwork.

These are regression checks, not OCR or a replacement for visual/game review.
Color ranges, regions and tolerances belong to the locale's artwork recipe.
"""
from collections import Counter


def _integer(value, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("Invalid artwork check integer")
    return value


def _points(image, selector):
    rect = selector["rect"]
    if not isinstance(rect, list) or len(rect) != 4:
        raise ValueError("Invalid artwork check rectangle")
    x, y, w, h = rect
    _integer(x, 0, image.width - 1); _integer(y, 0, image.height - 1)
    _integer(w, 1, image.width - x); _integer(h, 1, image.height - y)
    low, high = selector["rgba_min"], selector["rgba_max"]
    if len(low) != 4 or len(high) != 4:
        raise ValueError("Invalid artwork check color")
    for a, b in zip(low, high):
        _integer(a, 0, 255); _integer(b, a, 255)
    return {(xx, yy) for yy in range(y, y+h) for xx in range(x, x+w)
            if all(a <= c <= b for c, a, b in zip(image.getpixel((xx, yy)), low, high))}


def measure_ink(image, selector, *, min_row_pixels, min_column_pixels):
    _integer(min_row_pixels, 1, image.width)
    _integer(min_column_pixels, 1, image.height)
    points = _points(image, selector)
    rows = Counter(y for x, y in points)
    columns = Counter(x for x, y in points)
    points = {(x, y) for x, y in points
              if rows[y] >= min_row_pixels and columns[x] >= min_column_pixels}
    if not points:
        raise ValueError("Artwork state has no measurable ink")
    box = [min(x for x,y in points), min(y for x,y in points),
           max(x for x,y in points)+1, max(y for x,y in points)+1]
    return {"bbox": box, "width": box[2]-box[0], "height": box[3]-box[1]}


def check_state_pairs(image, checks):
    if image.mode != "RGBA" or not isinstance(checks, list):
        raise ValueError("Invalid artwork state check input")
    reports = []; seen = set()
    for check in checks:
        identifier = check["id"]
        if not isinstance(identifier, str) or not identifier or identifier in seen:
            raise ValueError("Invalid/duplicate artwork state check ID")
        seen.add(identifier)
        kwargs = {k: check[k] for k in ("min_row_pixels", "min_column_pixels")}
        states = [measure_ink(image, check[k], **kwargs) for k in ("normal", "selected")]
        errors = []
        for dimension in ("width", "height"):
            tolerance = _integer(check["max_"+dimension+"_difference"], 0, max(image.size))
            if abs(states[0][dimension] - states[1][dimension]) > tolerance:
                errors.append(f"{dimension} {states[0][dimension]}/{states[1][dimension]} differs by more than {tolerance}")
        run_report = []
        for strip in check.get("horizontal_runs", []):
            points = _points(image, strip)
            x, y, w, h = strip["rect"]
            longest = 0
            for yy in range(y, y+h):
                run = 0
                for xx in range(x, x+w):
                    run = run+1 if (xx, yy) in points else 0
                    longest = max(longest, run)
            if longest > _integer(strip["maximum"], 0, w):
                errors.append(f"horizontal run {longest} exceeds {strip['maximum']}")
            run_report.append(longest)
        if errors:
            raise ValueError(f"Artwork state check {identifier}: " + "; ".join(errors))
        reports.append({"id": identifier, "normal": states[0], "selected": states[1],
                        "horizontal_runs": run_report})
    return reports
