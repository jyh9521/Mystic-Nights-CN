"""Write reproducible, read-only font evidence from the supported original ISO.

The output records parsed resources, every glyph rectangle, exact code anchors
and embedded DWARF 1 function ranges. It neither executes nor modifies the game.
No disassembler, extracted game tree or private research output is required.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import struct

from _bootstrap import ROOT
from mysticnights.font import parse_fnt, parse_tim2, resource_hash
from mysticnights.resources import parse_res
from mysticnights.versions import load_version, verify_original


ELF_SHA256 = "a8662cb99c7dd8abc66c6766d27e0fc15ff83fb3a04d2837001b87f88cf899c4"
SYSTEM_SHA256 = "87d5c6bea0894e11f2927ed999cce9da46d69a7951538503e70c1f30c860adce"
FUNCTIONS = {
    "GetHashCode": (0x1488B0, 0x14890C),
    "BinarySearch": (0x155850, 0x1558E4),
    "RenderString": (0x155C70, 0x15663C),
    "LoadFont": (0x156640, 0x156820),
}
# Each anchor is deliberately short. These constants establish only the named
# instructions, not a substitute copy of a complete proprietary executable.
ANCHORS = (
    ("hash_seed_5381", "GetHashCode", 0x1488C4,
     "2b080200051506240a0020102d380000",
     "addiu a2, zero, 0x1505 initializes the hash to 5381"),
    ("hash_step", "GetHashCode", 0x1488D4,
     "2118070240210600000065800100e7242120a4002b18e200f9ff60142130c400",
     "shift by 5, signed lb, additions: hash = hash * 33 + signed byte"),
    ("two_byte_decoder", "RenderString", 0x155DD0,
     "ff0044308000823043014010010052262118720200120400000063900100522625204300",
     "lead & 0x80 selects a second byte; key = (lead << 8) | trail"),
    ("lookup_fixed_count_2539", "BinarySearch", 0x155850,
     "2d4000002d100000eb0907242b00063c8079c624",
     "addiu a3, zero, 0x09eb hard-codes the 2539-entry search ceiling"),
    ("lookup_key_compare", "BinarySearch", 0x15588C,
     "8018020021186200801803002118c300000065940900851000000000",
     "20-byte runtime glyph records; lhu reads the key for comparison"),
    ("load_count_u32", "LoadFont", 0x156664,
     "04000624de72040c004043a44c00a38f040052262a180300",
     "copies a four-byte count and advances the resource pointer by four"),
    ("load_record_stride_14", "LoadFont", 0x15679C,
     "0e005226",
     "addiu s2, s2, 14 advances one on-disc FNT record"),
    ("load_y_plus_one", "LoadFont", 0x156758,
     "0c0002860e0004260a0045260200062401004224de72040c0c0002a6",
     "loaded Y is incremented by one before storage"),
    ("load_height_minus_one", "LoadFont", 0x156784,
     "1000038601000424ffff6324100003a6",
     "loaded height is decremented by one before storage"),
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _slice(data: bytes, start: int, size: int, label: str) -> bytes:
    if start < 0 or size < 0 or start + size > len(data):
        raise ValueError(f"Out-of-bounds {label}")
    return data[start:start + size]


def _cstring(data: bytes, offset: int, label: str) -> tuple[str, int]:
    if not 0 <= offset < len(data):
        raise ValueError(f"Out-of-bounds {label}")
    end = data.find(b"\0", offset)
    if end == -1:
        raise ValueError(f"Unterminated {label}")
    return data[offset:end].decode("ascii"), end + 1


def _elf_layout(elf: bytes) -> tuple[dict[str, dict], list[dict]]:
    if elf[:7] != b"\x7fELF\x01\x01\x01" or len(elf) < 52:
        raise ValueError("Expected little-endian ELF32")
    if struct.unpack_from("<H", elf, 18)[0] != 8:
        raise ValueError("Expected MIPS ELF machine")
    phoff, shoff = struct.unpack_from("<II", elf, 28)
    phsize, phcount, shsize, shcount, names_index = struct.unpack_from("<5H", elf, 42)
    if phsize != 32 or shsize != 40 or names_index >= shcount:
        raise ValueError("Unexpected ELF table layout")
    sections_raw = [struct.unpack("<10I", _slice(elf, shoff + i * shsize, shsize, "section"))
                    for i in range(shcount)]
    names_header = sections_raw[names_index]
    names = _slice(elf, names_header[4], names_header[5], "section names")
    sections = {}
    for section in sections_raw:
        name, _ = _cstring(names, section[0], "section name")
        if name:
            if name in sections:
                raise ValueError("Duplicate named ELF section")
            sections[name] = {"offset": section[4], "size": section[5], "type": section[1]}
    loads = []
    for i in range(phcount):
        fields = struct.unpack("<8I", _slice(elf, phoff + i * phsize, phsize, "program header"))
        kind, offset, virtual, physical, file_size, memory_size, flags, alignment = fields
        if kind == 1:
            _slice(elf, offset, file_size, "load segment")
            loads.append({"offset": offset, "virtual_address": virtual,
                          "physical_address": physical, "file_size": file_size,
                          "memory_size": memory_size, "flags": flags, "alignment": alignment})
    return sections, loads


def _va_to_file(va: int, size: int, loads: list[dict]) -> int:
    matches = [p["offset"] + va - p["virtual_address"] for p in loads
               if p["virtual_address"] <= va
               and va + size <= p["virtual_address"] + p["file_size"]]
    if len(matches) != 1:
        raise ValueError(f"Ambiguous/unmapped code VA: {va:#x}")
    return matches[0]


def _dwarf1_attributes(record: bytes) -> dict[int, object]:
    """Read DWARF 1 forms 1..8; reject rather than guess unknown forms."""
    attributes = {}
    cursor = 6
    while cursor < len(record):
        attr, = struct.unpack("<H", _slice(record, cursor, 2, "DWARF attribute"))
        cursor += 2
        form = attr & 0xF
        if form in (1, 2, 5, 6, 7):
            size = {1: 4, 2: 4, 5: 2, 6: 4, 7: 8}[form]
            value = int.from_bytes(_slice(record, cursor, size, "DWARF scalar"), "little")
            cursor += size
        elif form in (3, 4):
            prefix = 2 if form == 3 else 4
            size = int.from_bytes(_slice(record, cursor, prefix, "DWARF block length"), "little")
            cursor += prefix
            value = _slice(record, cursor, size, "DWARF block")
            cursor += size
        elif form == 8:
            value, cursor = _cstring(record, cursor, "DWARF string")
        else:
            raise ValueError(f"Unsupported DWARF 1 form {form}")
        if attr in attributes:
            raise ValueError("Duplicate DWARF attribute")
        attributes[attr] = value
    return attributes


def _font_functions(elf: bytes, sections: dict[str, dict]) -> list[dict]:
    if ".debug" not in sections:
        raise ValueError("Expected embedded DWARF 1 .debug section")
    section = sections[".debug"]
    data = _slice(elf, section["offset"], section["size"], "DWARF section")
    cursor = 0
    found = {}
    while cursor < len(data):
        size = int.from_bytes(_slice(data, cursor, 4, "DWARF entry length"), "little")
        if size < 4:
            raise ValueError("Invalid DWARF entry size")
        record = _slice(data, cursor, size, "DWARF entry")
        if size > 4:
            tag, = struct.unpack("<H", _slice(record, 4, 2, "DWARF tag"))
            if tag in (0x06, 0x14):  # global_subroutine / subroutine
                attrs = _dwarf1_attributes(record)
                name = attrs.get(0x38)
                if name in FUNCTIONS and attrs.get(0x111) == FUNCTIONS[name][0]:
                    if attrs.get(0x121) != FUNCTIONS[name][1] or name in found:
                        raise ValueError(f"DWARF range mismatch/duplicate: {name}")
                    found[name] = {"name": name, "low_pc": attrs[0x111],
                                   "high_pc_exclusive": attrs[0x121],
                                   "debug_entry_file_offset": section["offset"] + cursor,
                                   "debug_entry_length": size, "tag": tag,
                                   "evidence": "embedded DWARF 1 name/low_pc/high_pc"}
        cursor += size
    if set(found) != set(FUNCTIONS):
        raise ValueError(f"Missing expected DWARF function: {sorted(set(FUNCTIONS) - set(found))}")
    return [found[name] for name in FUNCTIONS]


def inspect_font(image, version: dict) -> dict:
    elf = image.read("SCKA_200.55")
    system = image.read("RES/SYSTEM.RES")
    if sha256(elf) != ELF_SHA256 or sha256(system) != SYSTEM_SHA256:
        raise ValueError("Font investigation requires the recorded retail ELF and SYSTEM.RES")
    sections, loads = _elf_layout(elf)
    functions = _font_functions(elf, sections)
    anchors = []
    for name, function, va, expected_hex, meaning in ANCHORS:
        expected = bytes.fromhex(expected_hex)
        offset = _va_to_file(va, len(expected), loads)
        actual = _slice(elf, offset, len(expected), name)
        if actual != expected:
            raise ValueError(f"Expected machine bytes mismatch: {name}")
        lo, hi = FUNCTIONS[function]
        if not lo <= va < va + len(expected) <= hi:
            raise ValueError(f"Anchor outside expected function: {name}")
        anchors.append({"id": name, "function": function, "virtual_address": va,
                        "file_offset": offset, "length": len(expected),
                        "expected_hex": expected.hex(), "actual_hex": actual.hex(),
                        "matches": True, "interpretation": meaning,
                        "evidence": "exact retail machine-byte comparison; no runtime observation"})
    archive = parse_res(system)
    fnt_entry = archive.get("FONT.FNT")
    fnt = archive.read(fnt_entry)
    glyphs = parse_fnt(fnt)
    if len(glyphs) != 2539:
        raise ValueError("Retail fixed-count font must contain exactly 2539 records")
    textures = {}
    for number in range(1, 9):
        name = f"FONT_{number}.TM2"
        entry = archive.get(name)
        data = archive.read(entry)
        info = parse_tim2(data)
        if info.width != 256 or info.height != 256 or len(data) != 66624:
            raise ValueError(f"Unexpected retail font atlas dimensions: {name}")
        textures[resource_hash(name)] = {"name": name, "entry": entry, "data": data,
                                        "info": info, "occupied": bytearray(info.width * info.height),
                                        "glyphs": 0}
    if len(textures) != 8:
        raise ValueError("Font resource-name hash collision")
    records = []
    for index, glyph in enumerate(glyphs):
        if glyph.texture_hash not in textures:
            raise ValueError(f"Unknown glyph texture hash: {glyph.texture_hash:#x}")
        texture = textures[glyph.texture_hash]
        info = texture["info"]
        if glyph.x + glyph.width > info.width or glyph.y + glyph.height > info.height:
            raise ValueError(f"Glyph rectangle out of bounds: {glyph.code:#x}")
        if glyph.height != 14 or (glyph.code >= 128 and glyph.width != 13):
            raise ValueError(f"Unexpected retail glyph dimensions: {glyph.code:#x}")
        bitmap = texture["occupied"]
        for y in range(glyph.y, glyph.y + glyph.height):
            start = y * info.width + glyph.x
            if any(bitmap[start:start + glyph.width]):
                raise ValueError(f"Overlapping glyph rectangle: {glyph.code:#x}")
            bitmap[start:start + glyph.width] = b"\x01" * glyph.width
        texture["glyphs"] += 1
        raw_key = bytes([glyph.code]) if glyph.code < 128 else glyph.code.to_bytes(2, "big")
        records.append({"index": index, "record_offset_in_fnt": 4 + index * 14,
                        "record_offset_in_system_res": fnt_entry.offset + 4 + index * 14,
                        "code": glyph.code, "code_hex": f"{glyph.code:04X}",
                        "source_cp949": raw_key.decode("cp949"),
                        "texture": texture["name"], "texture_hash": glyph.texture_hash,
                        "stored_rectangle": {"x": glyph.x, "y": glyph.y,
                                             "width": glyph.width, "height": glyph.height},
                        "loaded_rectangle": {"x": glyph.x, "y": glyph.y + 1,
                                             "width": glyph.width, "height": glyph.height - 1},
                        "in_bounds": True, "overlaps_another_glyph": False})
    texture_records = []
    for name_hash, texture in textures.items():
        entry, data, info = texture["entry"], texture["data"], texture["info"]
        pixels = data[info.pixel_offset:info.pixel_offset + info.pixel_length]
        palette = data[info.palette_offset:info.palette_offset + info.palette_length]
        texture_records.append({"name": texture["name"], "resource_name_hash": name_hash,
                                "resource_name_hash_hex": f"{name_hash:08X}",
                                "member_header_offset": entry.header_offset,
                                "offset_in_system_res": entry.offset, "size": entry.size,
                                "sha256": sha256(data), "width": info.width, "height": info.height,
                                "pixel_offset_in_tim2": info.pixel_offset,
                                "pixel_length": info.pixel_length, "pixel_sha256": sha256(pixels),
                                "palette_offset_in_tim2": info.palette_offset,
                                "palette_length": info.palette_length, "palette_sha256": sha256(palette),
                                "palette_format": "RGBA32, CSM1 indices exchange bits 3 and 4",
                                "glyph_count": texture["glyphs"],
                                "occupied_rectangle_pixels": sum(texture["occupied"]),
                                "occupancy_bitmap_sha256": sha256(texture["occupied"])})
    categories = Counter("ascii" if g.code < 128 else "jamo" if 0xA4A1 <= g.code <= 0xA4FE
                         else "hangul" if 0xB0A1 <= g.code <= 0xC8FE else "other" for g in glyphs)
    if dict(categories) != {"ascii": 95, "jamo": 94, "hangul": 2350}:
        raise ValueError("Unexpected retail font code inventory")
    return {
        "schema_version": 1,
        "evidence_type": "read-only, version-locked static resource and machine-byte inspection",
        "game_executed": False,
        "source": {"serial": version["serial"], "iso": version["iso"],
                   "elf": {"path": "SCKA_200.55", "size": len(elf), "sha256": sha256(elf)},
                   "system": {"path": "RES/SYSTEM.RES", "size": len(system), "sha256": sha256(system)}},
        "fnt": {"name": fnt_entry.name, "member_header_offset": fnt_entry.header_offset,
                "offset_in_system_res": fnt_entry.offset, "size": len(fnt), "sha256": sha256(fnt),
                "count": len(glyphs), "count_size": 4, "record_size": 14,
                "record_format": "<IHHHHH: texture hash, key, x, y, width, height",
                "keys_sorted_unique": True, "code_categories": dict(categories)},
        "textures": texture_records,
        "glyph_rectangles": records,
        "proof": {"all_glyphs_checked": len(glyphs), "all_rectangles_in_bounds": True,
                  "overlapping_pixels": 0, "occupied_pixels": sum(sum(t["occupied"]) for t in textures.values()),
                  "method": "mark every stored rectangle pixel in a fresh per-texture occupancy bitmap; reject any previously marked pixel"},
        "elf_load_segments": loads,
        "dwarf1_functions": functions,
        "code_anchors": anchors,
        "limitations": ["Static evidence does not establish boot, gameplay, text layout or save compatibility.",
                        "Machine-byte interpretations concern only the recorded snippets; no full decompilation is claimed.",
                        "The fixed lookup count makes expanding FONT.FNT alone unsupported."],
        "references": ["https://dwarfstd.org/doc/dwarf_1_1_0.pdf"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iso", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="new JSON file; existing paths are rejected")
    args = parser.parse_args()
    try:
        if os.path.lexists(args.output) or args.output.resolve() == args.iso.resolve():
            raise FileExistsError(f"Output must be a new file distinct from input: {args.output}")
        version = load_version(ROOT / "assets/game-version.json")
        image = verify_original(args.iso, version)
        report = inspect_font(image, version)
        text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        if json.loads(args.output.read_text(encoding="utf-8")) != report:
            raise ValueError("Font inspection JSON readback mismatch")
    except (ValueError, OSError, KeyError, struct.error) as exc:
        parser.exit(2, f"FONT_INSPECTION_ERROR: {exc}\n")
    counts = report["fnt"]["code_categories"]
    print(f"FONT_INSPECTION glyphs={report['fnt']['count']} ascii={counts['ascii']} "
          f"jamo={counts['jamo']} hangul={counts['hangul']} textures={len(report['textures'])} "
          f"overlaps={report['proof']['overlapping_pixels']} anchors={len(report['code_anchors'])} "
          f"dwarf_functions={len(report['dwarf1_functions'])}")


if __name__ == "__main__":
    main()
