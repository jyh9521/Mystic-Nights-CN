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
    points={(xx, yy) for yy in range(y, y+h) for xx in range(x, x+w)
            if all(a <= c <= b for c, a, b in zip(image.getpixel((xx, yy)), low, high))}
    excluded=set()
    for point in selector.get('exclude_points',[]):
        if not isinstance(point,list) or len(point)!=2:
            raise ValueError('Invalid artwork material exclusion')
        xx,yy=point;_integer(xx,x,x+w-1);_integer(yy,y,y+h-1)
        if (xx,yy)in excluded:raise ValueError('Duplicate artwork material exclusion')
        excluded.add((xx,yy))
    return points-excluded


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


def check_clear_regions(image, checks):
    """Require reviewed sprite gutters to stay transparent, including dark halos.

    Glyph size checks alone miss old lettering/glow outside a replacement's
    ink bounds. Regions are explicit locale artwork data, not inferred/OCR.
    """
    if image.mode != "RGBA" or not isinstance(checks, list):
        raise ValueError("Invalid artwork clear-region input")
    reports = []; seen = set()
    for check in checks:
        identifier = check["id"]
        if not isinstance(identifier, str) or not identifier or identifier in seen:
            raise ValueError("Invalid/duplicate artwork clear-region ID")
        seen.add(identifier)
        maximum = _integer(check["max_alpha"], 0, 254)
        selector = {"rect": check["rect"], "rgba_min": [0, 0, 0, maximum + 1],
                    "rgba_max": [255, 255, 255, 255]}
        dirty = _points(image, selector)
        if dirty:
            raise ValueError(f"Artwork clear-region {identifier}: nontransparent pixels={len(dirty)}")
        reports.append({"id": identifier, "rect": check["rect"], "max_alpha": maximum,
                        "nontransparent_pixels": 0})
    return reports


def check_size_groups(image, checks):
    """Compare peer labels across different rows/states, not only each pair."""
    if image.mode != 'RGBA' or not isinstance(checks, list):
        raise ValueError('Invalid artwork size-group input')
    reports=[];seen=set()
    for check in checks:
        identifier=check['id']
        if not isinstance(identifier,str) or not identifier or identifier in seen:
            raise ValueError('Invalid/duplicate artwork size-group ID')
        seen.add(identifier)
        if not isinstance(check['members'],list) or len(check['members'])<2:
            raise ValueError('Artwork size-group needs at least two members')
        kwargs={k:check[k]for k in ('min_row_pixels','min_column_pixels')}
        rows=[measure_ink(image,member,**kwargs)for member in check['members']]
        heights=[r['height']for r in rows]
        tolerance=_integer(check['max_height_difference'],0,image.height)
        if max(heights)-min(heights)>tolerance:
            raise ValueError(f'Artwork size-group {identifier}: peer heights={heights}')
        if 'expected_height' in check:
            expected=_integer(check['expected_height'],1,image.height)
            if any(h!=expected for h in heights):
                raise ValueError(f'Artwork size-group {identifier}: heights={heights}, expected={expected}')
        reports.append({'id':identifier,'members':rows,'heights':heights})
    return reports


def check_shape_pairs(image, checks):
    """Require shared glyph silhouettes and measured alignment in both states.

    Centers are twice the pixel-edge coordinates, so a half-pixel center has
    an exact integer representation. Selectors describe face colors only.
    """
    if image.mode != 'RGBA' or not isinstance(checks,list):
        raise ValueError('Invalid artwork shape-pair input')
    reports=[];seen=set()
    for check in checks:
        identifier=check['id']
        if not isinstance(identifier,str) or not identifier or identifier in seen:
            raise ValueError('Invalid/duplicate artwork shape-pair ID')
        seen.add(identifier);shapes=[];states=[]
        for state in ('normal','selected'):
            selector=check[state];points=_points(image,selector)
            if not points:raise ValueError('Artwork shape pair has no face pixels')
            x0=min(x for x,y in points);y0=min(y for x,y in points)
            x1=max(x for x,y in points)+1;y1=max(y for x,y in points)+1
            center=selector['center_twice']
            if not isinstance(center,list) or len(center)!=2:
                raise ValueError('Invalid artwork alignment center')
            for c,dimension in zip(center,image.size):_integer(c,0,dimension*2)
            tolerance=_integer(check['max_center_error_twice'],0,max(image.size)*2)
            error=[abs(x0+x1-center[0]),abs(y0+y1-center[1])]
            if max(error)>tolerance:
                raise ValueError(f'Artwork shape-pair {identifier}: {state} center error={error}')
            shapes.append({(x-x0,y-y0)for x,y in points})
            states.append({'bbox':[x0,y0,x1,y1],'face_pixels':len(points),'center_error_twice':error})
        if shapes[0]!=shapes[1]:
            raise ValueError(f'Artwork shape-pair {identifier}: state silhouettes differ')
        reports.append({'id':identifier,'normal':states[0],'selected':states[1],'silhouette':'identical'})
    return reports
