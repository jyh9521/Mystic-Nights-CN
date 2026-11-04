"""Inspect retail PF fonts and optionally build a separate equal-size glyph copy.

All evidence is offline. The preview decodes generated font cells, not an
emulated network screen. A returned Unicode alias map is mandatory for text.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import tempfile
import textwrap

from _bootstrap import ROOT
from mysticnights.network_font import (
    EUROPEAN_SHA256, KOREAN_SHA256, NETWORK_ELF_SHA256,
    build_network_font, collect_protected_codepoints, encode_text, parse_pf,
    render_preview,
)
from mysticnights.versions import load_version, verify_original


# Small original-byte anchors. VA = file offset + 0xff000 in this ELF.
# R5900-specific instructions outside these anchors are not treated as a
# successful full disassembly by a generic MIPS decoder.
ANCHORS = (
    ("attach_header", 0x11C3EC, "0000a28c040040140000bfff0400a28c03004010", "AttachData rejects nonzero version words at +0/+4"),
    ("subfont_table", 0x11C438, "5800828c0800e0032d1000002a10a200fcff401080180500211883005c00628c0800e003", "global +0x58 count and +0x5c indexed relative offsets"),
    ("unicode_lookup", 0x11A4B4, "0000e48c0800e28c232024013c00038e2110440021180302401002002110430000004394250065102d2000020c00e28cda71040c21884300", "range first/map_base, u16 index at subfont+0x3c, FFFF missing, plus glyph_base"),
    ("metric_mode", 0x11A534, "1000028ec21002000100423005004010001911004400028e2110020203000010211043004400028e21100202", "flags bit 3 selects indexed 16-byte metrics or the shared record"),
    ("pixel_depth", 0x11C768, "1000828c0400032407004230c01002000800e0030a106200", "flags low 3 bits zero means 4 bits per pixel"),
    ("utf8_three_byte", 0x11C830, "f000a22c030040100f00a3300700001002000724", "E0..EF lead keeps 4 bits and consumes two continuation bytes"),
    ("utf8_continuation", 0x11C85C, "800008240000c590c000a230f9ff48140100c624801903003f00a230ffffe724f8ffe01425186200", "UTF-8 continuation validates 80..BF and appends 6 bits"),
    ("advance_metric", 0x11BCD8, "0c00438406004684002883446029804608004484", "signed metric at +0x0c is converted to floating point for advance"),
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inspect(image):
    elf = image.read("NETGUICD.ELF")
    if digest(elf) != NETWORK_ELF_SHA256:
        raise ValueError("Unknown NETGUICD.ELF")
    anchors = []
    for name, address, expected, meaning in ANCHORS:
        raw = bytes.fromhex(expected)
        offset = address - 0xFF000
        if elf[offset:offset + len(raw)] != raw:
            raise ValueError(f"Network code anchor mismatch: {name}")
        anchors.append({"name": name, "virtual_address": address, "file_offset": offset, "expected_hex": expected, "interpretation": meaning})
    if elf[0x3B37A8:0x3B37B8] != b"PsIIlibpfont1200" or elf[0x3B37B8:0x3B37C4].hex() != "f0c7110090c8110090b61100":
        raise ValueError("PFont library marker or UTF-8 function table mismatch")
    resources, fonts = [], {}
    for name in sorted(image.files):
        if name.startswith("NETGUI/") and name.count("/") == 1:
            raw = image.read(name)
            resources.append({"resource": name, "size": len(raw), "sha256": digest(raw), "header_hex": raw[:96].hex()})
            if name.endswith(".PF"):
                expected = {"NETGUI/KOREAN.PF": KOREAN_SHA256, "NETGUI/EUROPEAN.PF": EUROPEAN_SHA256}.get(name)
                if digest(raw) != expected:
                    raise ValueError(f"Unknown PF font: {name}")
                font = parse_pf(raw)
                fonts[name] = {
                    "name": font.name, "style": font.style, "ascent": font.ascent,
                    "descent": font.descent, "maximum_advance": font.maximum_advance,
                    "subfont_count": len(font.subfonts), "physical_glyphs": sum(s.glyph_count for s in font.subfonts),
                    "mapped_code_units": len(font.glyphs), "shadowed_code_units": list(font.shadowed_codepoints),
                    "subfonts": [{k: v for k, v in asdict(s).items() if k not in ("indices", "metrics")}
                                 | {"mapping_entries": len(s.indices), "metrics_count": len(s.metrics), "metrics_first_record": list(s.metrics[0])}
                                 for s in font.subfonts],
                }
    protected = collect_protected_codepoints(elf)
    report = {"source_elf_sha256": digest(elf), "resources": resources, "fonts": fonts,
              "code_anchors": anchors, "protected_codepoints": sorted(protected),
              "source_survey": "Complete printable UTF-8 NUL strings in all ELF32 PT_LOAD spans",
              "verified_format": {"library_marker": "PsIIlibpfont1200", "standard_outline_font": False,
                 "pixel_format": "4-bit linear indexed cells; low nibble first; each cell padded to 16 bytes",
                 "range_record": ["u32 first", "u32 last", "u32 map_base", "u32 glyph_base"],
                 "lookup": "glyph_base + u16_map[map_base + code_unit - first]; FFFF means absent",
                 "metrics": "16-byte record, signed s16 advance at +0x0c; other fields preserved without claiming every meaning",
                 "atlas": "separate fixed-size glyph cells, not a shared TIM2 atlas",
                 "palette": "16 RGBA entries; source alpha 0..125, PS2 0..128 convention",
                 "conversion_tables": "JIS2UCS.BIN and UCS2JIS.BIN are each 65536 little-endian u16 entries; the verified UTF-8 callback directly decodes Unicode"},
              "analysis_boundary": "REA bound the MIPS ELF but its Windows providers rejected native decompilation; anchors independently checked from original bytes.",
              "limitations": ["No game or network module was executed.",
                 "This parser covers only the two shipped uncompressed 4-bpp PF profiles, not every Sony PF variant.",
                 "The alias encoder is mandatory; writing unmodified Chinese UTF-8 would not use the newly drawn Hangul slots.",
                 "A source-static unused Hangul slot can still be entered dynamically in a saved/user-provided name; that dynamic coverage remains unverified.",
                 "Preview is a fixed-cell atlas readback, not runtime layout, wrapping, texture-cache or input-method acceptance.",
                 "JIS conversion tables and original Latin/symbol metrics are not modified."]}
    return report, protected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iso", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="New directory; existing work is never overwritten")
    parser.add_argument("--catalogue", type=Path, help="Optional translated network catalogue; also produce a PF glyph copy")
    parser.add_argument("--font", type=Path)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError(f"Output must be new: {args.output}")
    image = verify_original(args.iso, load_version(ROOT / "assets/game-version.json"))
    report, protected = inspect(image)
    print(f"BASELINE PASS pf_files=2 subfonts=47,4 mapped_code_units=11964,1104 protected={len(protected)}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    parent = args.output.parent.resolve()
    with tempfile.TemporaryDirectory(prefix=f".{args.output.name}-", dir=parent) as temporary:
        work = Path(temporary).resolve()
        if work.parent != parent or args.output.resolve().parent != parent:
            raise ValueError("Output escaped intended parent")
        if args.catalogue:
            raw = args.catalogue.read_bytes()
            catalogue = json.loads(raw)
            rows = catalogue["entries"]
            if not rows or len({r["id"] for r in rows}) != len(rows):
                raise ValueError("Empty or duplicate network catalogue")
            elf = image.read("NETGUICD.ELF")
            for row in rows:
                if row["status"] not in ("draft", "reviewed") or row["resource"] != "NETGUICD.ELF" or not row["target"]:
                    raise ValueError(f"Untranslated/non-network field: {row['id']}")
                source = row["source"].encode("utf-8")
                offset = row["offset"]
                if (type(offset) is not int or offset < 0 or row["id"] != f"NETGUICD.ELF@{offset:08x}"
                        or row["source_bytes"] != len(source) or row["source_sha256"] != digest(source)
                        or elf[offset:offset + len(source) + 1] != source + b"\0"):
                    raise ValueError(f"Network source mismatch: {row['id']}")
            spec = json.loads((ROOT / "assets/font-source.json").read_text(encoding="utf8"))
            font_path = args.font or ROOT / "build/fonts" / spec["filename"]
            built = build_network_font(image.read("NETGUI/KOREAN.PF"), [r["target"] for r in rows], font_path, spec["sha256"], protected_codepoints=protected)
            for row in rows:
                if len(encode_text(row["target"], built.mapping)) > row["source_bytes"]:
                    raise ValueError(f"Network UTF-8 capacity overflow: {row['id']}")
            (work / "MODIFIED_FILE.PF").write_bytes(built.data)
            if (work / "MODIFIED_FILE.PF").read_bytes() != built.data:
                raise OSError("PF copy readback failed")
            selected = [r for r in rows if len(r["target"]) < 42][:5]
            preview_text = "\n".join("\n".join(textwrap.wrap(line, 24) or [""]) for row in selected for line in row["target"].splitlines())
            preview = render_preview(built.data, preview_text, built.mapping, scale=3)
            from PIL import Image
            background = Image.new("RGBA", preview.size, (32, 36, 40, 255))
            background.alpha_composite(preview)
            background.convert("RGB").save(work / "glyph-preview.png")
            with Image.open(work / "glyph-preview.png") as saved:
                saved.verify()
            report["build"] = {"catalogue_sha256": digest(raw), "translated_fields": len(rows),
                               "source_pf_sha256": built.source_sha256, "modified_pf_sha256": digest(built.data),
                               "size": len(built.data), "font_sha256": built.font_sha256,
                               "pixel_size": built.pixel_size, "mapping": built.mapping,
                               "changed_glyphs": list(built.changed_glyphs), "preview_ids": [r["id"] for r in selected],
                               "verification": "equal length; exact glyph-only ranges; parsed metadata equal; text encode/decode and capacity checks pass"}
            print(f"MODIFIED PASS fields={len(rows)} mapped={len(built.mapping)} changed_glyphs={len(built.changed_glyphs)} size={len(built.data)} sha256={digest(built.data)}")
        report_text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        (work / "report.json").write_text(report_text, encoding="utf8", newline="\n")
        if (work / "report.json").read_text(encoding="utf8") != report_text:
            raise OSError("Report readback failed")
        if args.output.exists() or args.output.is_symlink():
            raise FileExistsError("Output appeared during inspection")
        work.rename(args.output)
    print(f"OUTPUT {args.output.resolve()}")


if __name__ == "__main__":
    main()
