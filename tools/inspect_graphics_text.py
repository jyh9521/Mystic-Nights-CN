"""Decode every supported retail TIM2 for offline visual text inventory.

This is an offline inspection/preview tool, never an ISO writer.  The
decoder deliberately accepts only the three single-image, linear profiles
observed on the supported disc.  Text recognition is a separate human review;
resource names and successful decoding never imply that a texture has text.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from _bootstrap import ROOT
from mysticnights.resources import parse_res
from mysticnights.versions import load_version, verify_original


from mysticnights.graphics import decode_tim2, build_graphics


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", "utf-8")
    if json.loads(path.read_text("utf-8")) != value:
        raise ValueError(f"JSON readback mismatch: {path}")


def contact_sheets(entries: list[dict], output: Path, label: str, *, columns=8, rows=8):
    from PIL import Image, ImageDraw, ImageOps

    pages = []
    per_page = columns * rows
    for first in range(0, len(entries), per_page):
        page = entries[first:first + per_page]
        canvas = Image.new("RGB", (columns * 160, rows * 160), (32, 32, 32))
        draw = ImageDraw.Draw(canvas)
        for index, entry in enumerate(page):
            image = Image.open(output / entry["preview"]).convert("RGBA")
            small = ImageOps.contain(image, (156, 132), Image.Resampling.NEAREST)
            left, top = (index % columns) * 160, (index // columns) * 160
            canvas.paste(small, (left, top + 26), small)
            draw.text((left + 1, top), f"#{entry['index']:04d} {entry['references'][0]['member'][:19]}", fill="white")
            draw.text((left + 1, top + 12), f"{entry['width']}x{entry['height']}", fill="#cccccc")
        name = f"{label}-{first // per_page + 1:02d}.png"
        canvas.save(output / name)
        pages.append({"path": name, "texture_indices": [x["index"] for x in page]})
    return pages


def inspect(iso: Path, output: Path, upstream: Path | None = None) -> dict:
    version = load_version(ROOT / "assets/game-version.json")
    image = verify_original(iso, version)
    if output.exists():
        raise ValueError("output directory already exists")
    output.mkdir(parents=True)
    (output / "png").mkdir()
    unique = {}
    references = []
    resource_count = 0
    upstream_changes = []
    for name in sorted(image.files):
        if not name.endswith(".RES"):
            continue
        source = image.read(name)
        archive = parse_res(source)
        resource_count += 1
        source_hash = hashlib.sha256(source).hexdigest()
        reference_archive = None
        if upstream and (upstream / name).is_file():
            reference_archive = parse_res((upstream / name).read_bytes())
        for member in archive.entries:
            if not member.name.endswith(".TM2"):
                continue
            data = archive.read(member)
            digest = hashlib.sha256(data).hexdigest()
            ref = {"resource": name, "resource_sha256": source_hash,
                   "member": member.name, "offset": member.offset,
                   "size": member.size, "sha256": digest}
            if reference_archive:
                candidate = next((x for x in reference_archive.entries if x.name == member.name), None)
                if candidate:
                    other = reference_archive.read(candidate)
                    other_hash = hashlib.sha256(other).hexdigest()
                    ref["upstream_sha256"] = other_hash
                    if other_hash != digest:
                        preview, meta = decode_tim2(other)
                        preview_name = f"upstream-{len(upstream_changes):03d}-{member.name}.png"
                        preview.save(output / "png" / preview_name)
                        upstream_changes.append({**ref, "upstream_preview": f"png/{preview_name}",
                                                 "upstream_profile": meta})
            references.append(ref)
            if digest not in unique:
                decoded, profile = decode_tim2(data)
                index = len(unique) + 1
                filename = f"png/{index:04d}-{member.name}.png"
                decoded.save(output / filename)
                unique[digest] = {"index": index, "sha256": digest, **profile,
                                  "preview": filename, "references": [],
                                  "review_status": "not_visually_reviewed"}
            unique[digest]["references"].append(ref)
    textures = list(unique.values())
    ui = [x for x in textures if any("/UI" in r["resource"] or r["resource"] in
          ("RES/LOGO.RES", "RES/SYSTEM.RES", "RES/SUBSYS.RES", "RES/NETSUB.RES")
          for r in x["references"])]
    ui_hashes = {x["sha256"] for x in ui}
    others = [x for x in textures if x["sha256"] not in ui_hashes]
    sheets = contact_sheets(ui, output, "ui") + contact_sheets(others, output, "world")
    graph_assets = []
    if upstream and (upstream / "GRAPHICS").is_dir():
        for file in sorted((upstream / "GRAPHICS").rglob("*")):
            if not file.is_file():
                continue
            digest = hashlib.sha256(file.read_bytes()).hexdigest()
            matches = [r for r in references if r.get("upstream_sha256") == digest]
            graph_assets.append({"path": file.relative_to(upstream).as_posix(),
                                 "size": file.stat().st_size, "sha256": digest,
                                 "exact_upstream_member_matches": matches})
    result = {"format": "mystic-nights-graphics-inspection", "version": 1,
              "source_iso": str(iso.resolve()), "source_iso_sha256": version["iso"]["sha256"],
              "resource_count": resource_count, "texture_references": len(references),
              "unique_textures": len(textures), "unique_ui_textures": len(ui),
              "decoded_profiles": dict(Counter(f"image={x['image_type']},clut={x['clut_type']}" for x in textures)),
              "textures": textures, "contact_sheets": sheets,
              "upstream_changed_textures": upstream_changes,
              "upstream_graphics_files": graph_assets,
              "limitations": ["Decoding is not OCR or in-game reachability proof.",
                              "Only RES TM2 payloads are decoded; non-TM2 carriers require separate review.",
                              "No game or emulator is launched; original ISO is read-only."]}
    write_json(output / "inventory.json", result)
    return result


def preview(iso: Path, output: Path, manifest_path: Path, locale_path: Path, font_path: Path) -> dict:
    """Rebuild reviewed rectangles and retain comparison images plus proofs."""
    from PIL import Image, ImageDraw

    version = load_version(ROOT / "assets/game-version.json")
    image = verify_original(iso, version)
    manifest = json.loads(manifest_path.read_text("utf-8"))
    from mysticnights.artwork import load_graphics_catalogue
    locale = load_graphics_catalogue(locale_path)
    if manifest["source_iso_sha256"] != version["iso"]["sha256"]:
        raise ValueError("graphics manifest targets a different disc")
    replacements, report = build_graphics(image, manifest, locale, font_path)
    output.mkdir(parents=True, exist_ok=False)
    comparisons = []
    for texture in manifest["textures"]:
        active = [s for s in texture["slots"] if s.get("install")]
        if not active:
            continue
        ref = texture["references"][0]
        original = parse_res(image.read(ref["resource"])).read(ref["member"])
        changed = parse_res(replacements[ref["resource"]]).read(ref["member"])
        before, info = decode_tim2(original)
        after, new_info = decode_tim2(changed)
        allowed = set()
        rectangles = texture.get("artwork_rectangles", [s["rect"] for s in active])
        for x, y, width, height in rectangles:
            allowed.update(info["pixel_offset"] + yy * info["width"] + xx
                           for yy in range(y, y + height) for xx in range(x, x + width))
        different = [n for n, (a, b) in enumerate(zip(original, changed)) if a != b]
        if (len(original) != len(changed) or info != new_info or not set(different) <= allowed
                or original[:info["pixel_offset"]] != changed[:info["pixel_offset"]]
                or original[info["palette_offset"]:] != changed[info["palette_offset"]:]):
            raise AssertionError("localized graphics changed unselected bytes or structure")
        name = texture["sha256"][:12]
        before.save(output / f"{name}-original.png")
        after.save(output / f"{name}-localized.png")
        sheet = Image.new("RGB", (before.width * 2, before.height + 24), (32, 32, 32))
        sheet.paste(before, (0, 24), before)
        sheet.paste(after, (before.width, 24), after)
        ImageDraw.Draw(sheet).text((4, 4), f"{ref['member']} original | {locale['locale']}", fill="white")
        sheet.save(output / f"{name}-compare.png")
        comparisons.append({"sha256": texture["sha256"], "resource": ref["resource"],
                            "member": ref["member"], "comparison": f"{name}-compare.png",
                            "modified_sha256": hashlib.sha256(changed).hexdigest(),
                            "changed_pixel_bytes": len(different), "palette_and_structure_unchanged": True})
    report.update(source_iso_sha256=version["iso"]["sha256"],
                  font_sha256=locale["font_sha256"], comparisons=comparisons,
                  changed_resources_hashes={name: hashlib.sha256(data).hexdigest()
                                            for name, data in replacements.items()})
    write_json(output / "verification.json", report)
    # Reopen the produced image files, not only the in-memory PIL objects.
    for row in comparisons:
        for suffix in ("original", "localized", "compare"):
            with Image.open(output / f"{row['sha256'][:12]}-{suffix}.png") as reopened:
                reopened.verify()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iso", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--upstream", type=Path)
    parser.add_argument("--preview-only", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--locale", type=Path)
    parser.add_argument("--font", type=Path)
    args = parser.parse_args()
    if args.preview_only:
        if not all((args.manifest, args.locale, args.font)):
            parser.error("--preview-only requires --manifest, --locale and --font")
        result = preview(args.iso, args.output, args.manifest, args.locale, args.font)
        print(f"installed slots: {len(result['installed_slots'])}; pending slots: {len(result['pending_art_restoration_slots'])}; changed texture members: {result['changed_texture_members']}")
        return
    if any((args.manifest, args.locale, args.font)):
        parser.error("manifest/locale/font are only valid with --preview-only")
    result = inspect(args.iso, args.output, args.upstream)
    print(json.dumps({key: result[key] for key in ("resource_count", "texture_references",
          "unique_textures", "unique_ui_textures", "decoded_profiles")}, indent=2))
    print(f"changed upstream textures: {len(result['upstream_changed_textures'])}")


if __name__ == "__main__":
    main()
