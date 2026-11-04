"""Verify disc identity, fixed-slot text, font isolation and unchanged resources.

All checks are offline. Passing is not a claim that a game was started or that
menus, saves, dialogue progression or a full playthrough were exercised.
"""
import argparse
import hashlib
import json
from pathlib import Path

from _bootstrap import ROOT
from mysticnights.font import decode_text, encode_text, parse_fnt, parse_tim2, resource_hash
from mysticnights.iso9660 import IsoImage, sha256_file
from mysticnights.localization import load_catalogue
from mysticnights.resources import parse_res
from mysticnights.scripts import extract_strings, patch_strings
from mysticnights.versions import load_version, verify_original


def require(value, message):
    if not value:
        raise ValueError(message)


def verification_font_path(manifest, override: Path | None = None) -> Path:
    """Select the rerender input and bind its bytes to the recorded build."""
    digest = manifest["font"].get("sha256")
    require(isinstance(digest, str) and len(digest) == 64 and all(c in "0123456789abcdef" for c in digest),
            "Invalid manifest font hash")
    if override is not None:
        path = Path(override)
    else:
        locale = manifest.get("locale")
        require(isinstance(locale, str) and bool(locale)
                and all(c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for c in locale),
                "Invalid manifest locale")
        config = json.loads((ROOT / "locales" / locale / "config.json").read_text(encoding="utf8"))
        require(config.get("locale") == locale, "Font locale configuration mismatch")
        relative = Path(config["font_spec"])
        source = (ROOT / relative).resolve()
        require(not relative.is_absolute() and ".." not in relative.parts and source.is_relative_to(ROOT.resolve()),
                "Font source configuration escapes repository")
        spec = json.loads(source.read_text(encoding="utf8"))
        require(spec.get("sha256") == digest, "Font source configuration/manifest hash mismatch")
        filename = spec["filename"]
        require(isinstance(filename, str) and bool(filename) and Path(filename).name == filename
                and filename not in {".", ".."}, "Invalid configured font filename")
        path = ROOT / "build/fonts" / filename
    require(sha256_file(path) == digest, "Verification font hash mismatch")
    return path


def only_ranges(before: bytes, after: bytes, ranges) -> None:
    require(len(before) == len(after), "Resource size changed")
    end = 0
    for start, stop in sorted(ranges):
        require(0 <= start < stop <= len(before), "Invalid allowed change range")
        if start > end:
            require(before[end:start] == after[end:start], f"Unexpected bytes outside intended edits at {end:#x}")
        end = max(end, stop)
    require(before[end:] == after[end:], f"Unexpected bytes after intended edits at {end:#x}")


def original_slots(image, entries):
    for row in entries:
        data = image.read(row["resource"])
        if row["kind"] == "script":
            data = parse_res(data).read(row["member"])
            expected = row["source"].encode("cp949")
        else:
            expected = row["source"].encode("cp949") + b"\0" * (1 + row.get("padding_bytes", 0))
        require(len(expected) == row["capacity"], f"Catalogue capacity mismatch: {row['id']}")
        require(data[row["offset"]:row["offset"] + row["capacity"]] == expected, f"Source mismatch: {row['id']}")


def baseline(image, entries):
    resources = scripts = 0
    for path in sorted(image.files):
        if path.endswith(".RES"):
            original = image.read(path)
            archive = parse_res(original)
            require(archive.replace({}) == original, f"Resource round trip failed: {path}")
            resources += 1
            for member in archive.entries:
                if member.name.endswith(".SCR"):
                    data = archive.read(member)
                    records = extract_strings(data, member.name)
                    replacements = {r.id: r.source for r in records if r.role == "display" and r.source}
                    require(patch_strings(data, records, replacements) == data, f"Script round trip failed: {path}/{member.name}")
                    scripts += 1
    original_slots(image, entries)
    print(f"BASELINE PASS files={len(image.files)} resources={resources} scripts={scripts} source_slots={len(entries)}")
    print(f"SHA256 {sha256_file(image.path)}")


def verify_full_paths(original, image, manifest, ranges, *, font_path: Path | None = None):
    """Independently rebuild name closures and both auxiliary display domains."""
    from mysticnights.auxiliary import patch_auxiliary_slots
    from mysticnights.linked_names import discover_name_links
    from mysticnights.network_font import (collect_protected_codepoints, parse_pf, allocate_mapping,
                                          encode_text as encode_network, decode_text as decode_network, decode_glyph)
    full = manifest["full_text"]
    mapping = manifest["font"]["mapping"]
    links = discover_name_links(original)
    require(links["core_sha256"] == full["name_links_sha256"], "Name source closure mismatch")
    targets = {r["id"]: r for r in full["names"]}
    require(len(targets) == len(full["names"]) == len(links["groups"]), "Incomplete/duplicate linked-name set")
    require(len({r["target"] for r in targets.values()}) == len(targets), "Translated name collision")
    count = 0
    for group in links["groups"]:
        row = targets[group["id"]]
        require(row["source"] == group["source"], "Name original source changed")
        target = encode_text(row["target"], mapping)
        require(len(target) <= group["max_encoded_bytes"], "Name capacity exceeded")
        for reference in group["references"]:
            begin, size = reference["offset"], reference["capacity"]
            wanted = (target + (b"\0" if reference["capacity_includes_nul"] else b"")).ljust(size, b"\0")
            actual = image.read(reference["resource"])[begin:begin + size]
            require(actual == wanted, f"Name reference mismatch: {group['id']}/{reference['resource']}@{begin:x}")
            ranges.setdefault(reference["resource"], []).append((begin, begin + size))
            count += 1
    auxiliary, network = full["auxiliary"], full["network_font"]
    protected = collect_protected_codepoints(original.read("NETGUICD.ELF"))
    require(set(network["protected_codepoints"]) == protected, "Network source protection mismatch")
    before_pf, after_pf = original.read("NETGUI/KOREAN.PF"), image.read("NETGUI/KOREAN.PF")
    require(hashlib.sha256(before_pf).hexdigest() == network["source_sha256"], "PF original hash mismatch")
    old, new = parse_pf(before_pf), parse_pf(after_pf)
    require(old.subfonts == new.subfonts and old.glyphs == new.glyphs, "PF lookup/metrics/palette changed")
    actual_mapping = allocate_mapping(old, [r["target"] for r in auxiliary["network"]], protected_codepoints=protected)
    require(network["mapping"] == actual_mapping, "Network glyph assignment mismatch")
    aliased = {c: code for c, code in actual_mapping.items() if code != ord(c)}
    edits = {r["character"]: r for r in network["changed_glyphs"]}
    require(set(edits) == set(aliased) and len(edits) == len(network["changed_glyphs"]), "PF glyph edit set mismatch")
    for char, code in aliased.items():
        glyph = old.glyphs[code]
        start, size = glyph.offset, (glyph.width * glyph.height + 1) // 2
        row = edits[char]
        require((row["unicode_slot"], row["offset"], row["size"]) == (code, start, size), "PF glyph location changed")
        require(hashlib.sha256(before_pf[start:start + size]).hexdigest() == row["before_sha256"], "PF glyph original mismatch")
        require(hashlib.sha256(after_pf[start:start + size]).hexdigest() == row["after_sha256"], "PF glyph output mismatch")
        require(code not in protected and decode_glyph(new, code).getbbox() is not None, "Protected/blank PF glyph")
        ranges.setdefault("NETGUI/KOREAN.PF", []).append((start, start + size))
    for key, resource, encoder, plain in (
            ("network", "NETGUICD.ELF", lambda text: encode_network(text, network["mapping"]), False),
            ("agreement", "DATA/AGREE.TXT", lambda text: encode_text(text, mapping), True)):
        rows = auxiliary[key]
        expected = patch_auxiliary_slots(original.read(resource), rows, encoder, plain=plain)
        require(image.read(resource) == expected, f"Auxiliary text readback mismatch: {resource}")
        for row in rows:
            start, size = row["offset"], row["source_bytes"] + (not plain)
            ranges.setdefault(resource, []).append((start, start + size))
            decoder = decode_text if plain else decode_network
            code_map = mapping if plain else network["mapping"]
            require(decoder(expected[start:start + size].rstrip(b"\0"), code_map) == row["target"], "Auxiliary Unicode round trip failed")
    if full.get("save_metadata"):
        from mysticnights.save_metadata import build_save_metadata, parse_icon_sys
        metadata = full["save_metadata"]
        changes = build_save_metadata(original, metadata["recipe"], metadata["catalogue"])
        for name, payload in changes.items():
            require(image.read(name) == payload, "Save metadata readback mismatch")
            ranges.setdefault(name, []).extend([(6, 8), (0xC0, 0x104)])
            require(parse_icon_sys(payload).title == metadata["catalogue"]["entries"][0]["target"], "Firmware title decoding mismatch")
        preserved = metadata["recipe"]["evidence"]["main_save_title_unchanged"]
        start, size = preserved["offset"], preserved["capacity_with_nul"]
        require(image.read(preserved["resource"])[start:start + size] == original.read(preserved["resource"])[start:start + size],
                "Game save ASCII title changed unexpectedly")
    if full.get("graphics"):
        from mysticnights.graphics import build_graphics, decode_tim2
        graphics = full["graphics"]
        require(graphics["catalogue"]["font_sha256"] == manifest["font"]["sha256"], "Graphics/manifest font hash mismatch")
        font_path = verification_font_path(manifest, font_path)
        expected_graphics, actual_report = build_graphics(original, graphics["recipe"], graphics["catalogue"], font_path)
        require(actual_report == graphics["report"], "Graphics coverage/report mismatch")
        for texture in graphics["recipe"]["textures"]:
            slots = [slot for slot in texture["slots"] if slot.get("install")]
            if not slots:
                continue
            for ref in texture["references"]:
                expected_archive = parse_res(expected_graphics[ref["resource"]])
                actual_archive = parse_res(image.read(ref["resource"]))
                payload = actual_archive.read(ref["member"])
                require(payload == expected_archive.read(ref["member"]), f"Graphics rerender mismatch: {ref['resource']}/{ref['member']}")
                _, info = decode_tim2(payload)
                rectangles = texture.get("artwork_rectangles", [s["rect"] for s in slots])
                for x, y, width, height in rectangles:
                    for row in range(y, y + height):
                        start = ref["offset"] + info["pixel_offset"] + row * info["width"] + x
                        ranges.setdefault(ref["resource"], []).append((start, start + width))
        print(f"GRAPHICS PASS translated={len(graphics['catalogue']['entries'])} installed={len(actual_report['installed_slots'])} pending={len(actual_report['pending_art_restoration_slots'])} texture_members={actual_report['changed_texture_members']} save_metadata={len(full.get('save_metadata', {}).get('catalogue', {}).get('entries', []))}")
    if full.get("raw_images"):
        from mysticnights.raw_images import build_raw_images
        raw = full["raw_images"]
        expected_raw, raw_report = build_raw_images(original, raw["recipe"], raw["catalogue"])
        require(raw_report == raw["report"], "Raw image coverage/report mismatch")
        for row in raw["recipe"]["images"]:
            resource = row["resource"]
            require(image.read(resource) == expected_raw[resource], f"Raw image replay mismatch: {resource}")
            width = row["profile"][0]
            for slot in row["slots"]:
                x, y, w, h = slot["rect"]
                for yy in range(y, y + h):
                    start = (yy * width + x) * 3
                    ranges.setdefault(resource, []).append((start, start + w * 3))
        print(f"RAW_IMAGES PASS installed={len(raw_report['installed_slots'])} resources={len(expected_raw)}")
    print(f"FULL_PATHS PASS names={len(targets)} references={count} network_strings={len(auxiliary['network'])} network_glyphs={len(network['mapping'])} agreement=1 extra_interface={len(auxiliary['extra_interface'])}")


def modified(original, image, manifest, *, font_path: Path | None = None):
    require(sha256_file(image.path) == manifest["modified"]["sha256"], "Modified ISO hash mismatch")
    require(image.size == manifest["modified"]["size"], "Modified ISO size mismatch")
    require(image.files == original.files and image.directories == original.directories, "ISO LBA/records changed")
    entries = manifest["entries"]
    original_slots(original, entries)
    mapping = manifest["font"]["mapping"]
    require(len(mapping) == len(set(mapping.values())), "Duplicate glyph assignments")
    ranges = {"RES/SYSTEM.RES": []}
    for row in entries:
        data = image.read(row["resource"])
        member_base = 0
        if row["kind"] == "script":
            archive = parse_res(data)
            member = archive.get(row["member"])
            member_base = member.offset
            data = archive.read(member)
        slot = data[row["offset"]:row["offset"] + row["capacity"]]
        require(slot == encode_text(row["target"], mapping).ljust(row["capacity"], b"\0"), f"Target readback mismatch: {row['id']}")
        require(decode_text(slot.rstrip(b"\0"), mapping) == row["target"], f"Text decoding mismatch: {row['id']}")
        begin = member_base + row["offset"]
        ranges.setdefault(row["resource"], []).append((begin, begin + row["capacity"]))
    if manifest.get("full_text"):
        verify_full_paths(original, image, manifest, ranges, font_path=font_path)
    system = parse_res(original.read("RES/SYSTEM.RES"))
    patched_system = parse_res(image.read("RES/SYSTEM.RES"))
    require(system.entries == patched_system.entries, "SYSTEM member table changed")
    require(system.read("FONT.FNT") == patched_system.read("FONT.FNT"), "FNT mapping/metrics changed")
    glyphs = {g.code: g for g in parse_fnt(system.read("FONT.FNT"))}
    textures = {resource_hash(f"FONT_{n}.TM2"): system.get(f"FONT_{n}.TM2") for n in range(1, 9)}
    policy = manifest["font"].get("protection_policy", "poc-source-text")
    protected = set(manifest["font"].get("protected_codes", manifest["font"].get("protected_jamo_codes", [])))
    if policy == "retained-display-text":
        from mysticnights.font_usage import collect_full_protected_codes
        full = manifest["full_text"]
        actual_protected, _ = collect_full_protected_codes(original.path, load_version(ROOT / "assets/game-version.json"), entries,
            name_targets={r["id"]: r["target"] for r in full["names"]},
            plaintext_replacements={r["resource"]: r for r in full["auxiliary"]["agreement"]})
        require(protected == set(actual_protected), "Retained-display font protection mismatch")
    elif policy == "source-text-survey":
        from mysticnights.font_usage import collect_protected_codes
        actual_protected, _ = collect_protected_codes(original.path, load_version(ROOT / "assets/game-version.json"))
        require(protected == set(actual_protected), "Font protection survey mismatch")
    elif policy != "poc-source-text":
        raise ValueError(f"Unknown font protection policy: {policy}")
    for code in mapping.values():
        require(type(code) is int and code in glyphs and code > 127 and code not in protected, "Overwrote protected or unknown font glyph")
        if policy == "poc-source-text":
            require(0xA4A1 <= code <= 0xA4FE, "Legacy PoC overwrote a non-Jamo glyph")
        glyph = glyphs[code]
        member = textures[glyph.texture_hash]
        texture = system.read(member)
        changed_texture = patched_system.read(member)
        info = parse_tim2(texture)
        visible = False
        for y in range(glyph.height):
            offset = info.pixel_offset + (glyph.y + y) * info.width + glyph.x
            begin = member.offset + offset
            ranges["RES/SYSTEM.RES"].append((begin, begin + glyph.width))
            for value in changed_texture[offset:offset + glyph.width]:
                color = info.palette[value]
                visible |= bool(color[3] and max(color[:3]))
        require(visible, f"Blank Chinese glyph at {code:04x}")
    expected = {row["path"]: row for row in manifest["changed_files"]}
    require(len(expected) == len(manifest["changed_files"]), "Duplicate modified-file record")
    require(set(expected) == set(ranges), "Manifest changed-file set mismatch")
    changed = []
    for name in sorted(image.files):
        before, after = original.read(name), image.read(name)
        if before != after:
            changed.append(name)
            require(name in ranges, f"Unexpected changed file: {name}")
            only_ranges(before, after, ranges[name])
            require(hashlib.sha256(after).hexdigest() == expected[name]["sha256"], f"Modified member hash mismatch: {name}")
            if name.endswith(".RES"):
                require(parse_res(before).entries == parse_res(after).entries, f"Resource structure changed: {name}")
    require(set(changed) == set(expected), "Expected resources were not changed")
    print(f"MODIFIED PASS strings={len(entries)} glyphs={len(mapping)} changed_files={len(changed)} unchanged_files={len(image.files)-len(changed)} lba=unchanged")
    print(f"SHA256 {manifest['modified']['sha256']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iso", required=True, type=Path)
    parser.add_argument("--kind", choices=("baseline", "modified"), required=True)
    parser.add_argument("--original", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--locale", default="zh-CN")
    parser.add_argument("--font", type=Path, help="Font used for independent graphics rerender; must match manifest font SHA-256")
    args = parser.parse_args()
    version = load_version(ROOT / "assets/game-version.json")
    if args.kind == "baseline":
        if not args.locale or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for c in args.locale):
            parser.error("Invalid locale identifier")
        locale_dir = ROOT / "locales" / args.locale
        config = json.loads((locale_dir / "config.json").read_text(encoding="utf-8"))
        catalogue = load_catalogue(locale_dir / config["translations"])
        if catalogue["profile"] == "full-text":
            from mysticnights.auxiliary import extra_elf_entries
            extra = json.loads((locale_dir / config["extra_interface"]).read_text(encoding="utf8"))["entries"]
            catalogue["entries"] += extra_elf_entries(extra)
        baseline(verify_original(args.iso, version), catalogue["entries"])
    else:
        if not args.original or not args.manifest:
            parser.error("modified requires --original and --manifest")
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        require(manifest["original"] == version["iso"], "Manifest original identity mismatch")
        modified(verify_original(args.original, version), IsoImage(args.iso), manifest, font_path=args.font)


if __name__ == "__main__":
    main()
