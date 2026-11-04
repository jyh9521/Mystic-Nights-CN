"""Synthetic, redistribution-free tests for font-slot overlays."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mysticnights.font import (FontError, allocate_codes, decode_text, encode_text,
                              parse_fnt, parse_tim2, patch_glyphs, resource_hash)


def fnt_fixture():
    records = [(resource_hash("FONT_8.TM2"), 0x41, 1, 0, 5, 14),
               (resource_hash("FONT_8.TM2"), 0xA4A1, 8, 0, 13, 14),
               (resource_hash("FONT_8.TM2"), 0xA4A2, 23, 0, 13, 14)]
    return struct.pack("<I", len(records)) + b"".join(
        struct.pack("<IHHHHH", *record) for record in records)


def tim2_fixture():
    data = bytearray(16 + 48 + 256 * 256 + 1024)
    data[:8] = b"TIM2\x04\x00\x01\x00"
    struct.pack_into("<IIIHH4BHH", data, 16, len(data) - 16,
                     1024, 65536, 48, 256, 0, 1, 3, 5, 256, 256)
    data[64:65600] = bytes([255]) * 65536
    data[65600 + 4 * 255:65600 + 4 * 256] = bytes([128, 128, 128, 128])
    return bytes(data)


class FontTests(unittest.TestCase):
    def test_resource_hash_matches_all_retail_font_names(self):
        hashes = [0x624EA6CD, 0x6260BF4E, 0x6272D7CF, 0x6284F050,
                  0x629708D1, 0x62A92152, 0x62BB39D3, 0x62CD5254]
        self.assertEqual([resource_hash(f"FONT_{i}.TM2") for i in range(1, 9)], hashes)

    def test_fnt_count_and_order(self):
        self.assertEqual(len(parse_fnt(fnt_fixture())), 3)
        with self.assertRaises(FontError):
            parse_fnt(fnt_fixture()[:-1])
        data = bytearray(fnt_fixture())
        struct.pack_into("<H", data, 4 + 14 + 4, 0x41)
        with self.assertRaises(FontError):
            parse_fnt(bytes(data))

    def test_allocation_protected_slots_and_stability(self):
        glyphs = parse_fnt(fnt_fixture())
        mapping = allocate_codes(["中A"], glyphs, forbidden_codes=[0xA4A1])
        self.assertEqual(mapping, {"中": 0xA4A2})
        self.assertEqual(allocate_codes(["中文"], glyphs, existing_mapping=mapping),
                         {"中": 0xA4A2, "文": 0xA4A1})
        with self.assertRaises(FontError):
            allocate_codes(["中文标"], glyphs)
        with self.assertRaises(FontError):
            allocate_codes([], glyphs, forbidden_codes=[0xA4A2], existing_mapping=mapping)
        self.assertEqual(allocate_codes(["中"], glyphs, allowed_codes=[0xA4A2]),
                         {"中": 0xA4A2})
        with self.assertRaises(FontError):
            allocate_codes(["中文"], glyphs, allowed_codes=[0xA4A2])

    def test_encoding_roundtrip_and_ascii_tokens(self):
        mapping = {"中": 0xA4A1, "文": 0xA4A2}
        source = "<T>中文 %s\nA"
        encoded = encode_text(source, mapping)
        self.assertEqual(encoded, b"<T>\xa4\xa1\xa4\xa2 %s\nA")
        self.assertEqual(decode_text(encoded, mapping), source)
        for bad in ("未", "\x00"):
            with self.assertRaises(FontError):
                encode_text(bad, mapping)
        for bad in (b"\xa4", b"\xa4\xa3", b"\x00"):
            with self.assertRaises(FontError):
                decode_text(bad, mapping)

    def test_bad_mapping_is_rejected(self):
        with self.assertRaises(FontError):
            encode_text("中", {"中": 0x8000})
        with self.assertRaises(FontError):
            allocate_codes([], parse_fnt(fnt_fixture()), existing_mapping={"中": 0x41})

    def test_tim2_clut_bit_swap_and_length_guards(self):
        data = bytearray(tim2_fixture())
        data[65600 + 16 * 4:65600 + 17 * 4] = bytes([10, 20, 30, 40])
        self.assertEqual(parse_tim2(bytes(data)).palette[8], (10, 20, 30, 40))
        with self.assertRaises(FontError):
            parse_tim2(bytes(data[:-1]))
        data[35] = 4
        with self.assertRaises(FontError):
            parse_tim2(bytes(data))

    def test_overlay_preserves_headers_palette_ascii_and_other_cells(self):
        from PIL import Image
        original = tim2_fixture()
        patched = patch_glyphs(fnt_fixture(), {"FONT_8.TM2": original},
                               {"中": 0xA4A1}, {"中": Image.new("L", (13, 13), 255)})
        result = patched["FONT_8.TM2"]
        self.assertEqual(len(result), len(original))
        differences = {i for i, (a, b) in enumerate(zip(original, result)) if a != b}
        self.assertEqual(differences, set(range(64 + 8, 64 + 21)))
        self.assertEqual(result[:64], original[:64])
        self.assertEqual(result[65600:], original[65600:])
        self.assertEqual(parse_fnt(fnt_fixture()), parse_fnt(fnt_fixture()))
        with self.assertRaises(FontError):
            patch_glyphs(fnt_fixture(), {"FONT_8.TM2": original},
                         {"中": 0xA4A1}, {"中": Image.new("L", (14, 13))})

    def test_empty_overlay_is_byte_identical(self):
        source = {"FONT_8.TM2": tim2_fixture()}
        self.assertEqual(patch_glyphs(fnt_fixture(), source, {}, {}), source)


if __name__ == "__main__":
    unittest.main()
