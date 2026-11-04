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
            expected = row["source"].encode("cp949") + b"\0"
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


def modified(original, image, manifest):
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
    system = parse_res(original.read("RES/SYSTEM.RES"))
    patched_system = parse_res(image.read("RES/SYSTEM.RES"))
    require(system.entries == patched_system.entries, "SYSTEM member table changed")
    require(system.read("FONT.FNT") == patched_system.read("FONT.FNT"), "FNT mapping/metrics changed")
    glyphs = {g.code: g for g in parse_fnt(system.read("FONT.FNT"))}
    textures = {resource_hash(f"FONT_{n}.TM2"): system.get(f"FONT_{n}.TM2") for n in range(1, 9)}
    policy = manifest["font"].get("protection_policy", "poc-source-text")
    protected = set(manifest["font"].get("protected_codes", manifest["font"].get("protected_jamo_codes", [])))
    if policy == "source-text-survey":
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
    args = parser.parse_args()
    version = load_version(ROOT / "assets/game-version.json")
    if args.kind == "baseline":
        if not args.locale or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for c in args.locale):
            parser.error("Invalid locale identifier")
        locale_dir = ROOT / "locales" / args.locale
        config = json.loads((locale_dir / "config.json").read_text(encoding="utf-8"))
        catalogue = load_catalogue(locale_dir / config["translations"])
        baseline(verify_original(args.iso, version), catalogue["entries"])
    else:
        if not args.original or not args.manifest:
            parser.error("modified requires --original and --manifest")
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        require(manifest["original"] == version["iso"], "Manifest original identity mismatch")
        modified(verify_original(args.original, version), IsoImage(args.iso), manifest)


if __name__ == "__main__":
    main()
