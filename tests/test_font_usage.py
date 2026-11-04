"""Synthetic CP949 survey tests; no original game data is redistributed."""
from pathlib import Path
import random
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mysticnights.font_usage import (cp949_code_positions, elf_load_segments, is_printable_text, printable_cstrings,
                                raw_pair_hits, suffix_code_candidates)


class FontUsageTests(unittest.TestCase):
    def test_exact_source_tokens_not_cross_character_pairs(self):
        data = "거각".encode("cp949")
        self.assertEqual(data, bytes.fromhex("b0c5b0a2"))
        slots = {0xB0C5, 0xB0A2, 0xC5B0}
        self.assertEqual(list(cp949_code_positions(data, slots)), [(0, 0xB0C5), (2, 0xB0A2)])
        self.assertEqual(raw_pair_hits(data, slots), {0xB0C5: 0, 0xC5B0: 1, 0xB0A2: 2})

    def test_invalid_cp949_fails_without_replacement(self):
        with self.assertRaises(UnicodeDecodeError):
            list(cp949_code_positions(b"prefix\xff", {0xB0A1}))

    def test_comments_unquoted_fields_and_padding_are_not_filtered(self):
        data = b'SCR_TYPE TEST\n; ' + "가".encode("cp949") + b'\nUNKNOWN ' + "나".encode("cp949") + b'\0'
        expected = {int.from_bytes(c.encode("cp949"), "big") for c in "가나"}
        self.assertEqual({code for _, code in cp949_code_positions(data, expected)}, expected)

    def test_whole_cstrings_keep_offsets_and_reject_controls(self):
        ga = "가".encode("cp949")
        data = b"\0" + ga + b"\0bad\x01\0" + ga
        result = list(printable_cstrings(data))
        self.assertEqual(result, [(1, ga, "가")])

    def test_newline_tab_and_fullwidth_space_are_printable(self):
        self.assertTrue(is_printable_text("가\t나\r\n　"))
        self.assertFalse(is_printable_text("가\x00"))
        self.assertFalse(is_printable_text("가\x01"))
        self.assertFalse(is_printable_text(""))

    def test_suffix_after_binary_prefix_is_protected(self):
        ga = "가".encode("cp949")
        data = b"\x01\xff" + ga + b" A\0"
        self.assertEqual(list(printable_cstrings(data)), [])
        result = list(suffix_code_candidates(data, {0xB0A1}))
        self.assertEqual(result, [(2, 0xB0A1, 6)])
        for offset, _, end in result:
            self.assertTrue(is_printable_text(data[offset:end].decode("cp949")))

    def test_invalid_or_unterminated_suffix_not_protected(self):
        ga = "가".encode("cp949")
        self.assertEqual(list(suffix_code_candidates(ga + b"\x01\0", {0xB0A1})), [])
        self.assertEqual(list(suffix_code_candidates(ga, {0xB0A1})), [])

    def test_suffix_scanner_matches_bruteforce(self):
        cases = [b"\0", "가나 A".encode("cp949") + b"\0",
                 bytes.fromhex("b0c5b0a24100"), bytes.fromhex("ff01b0a100b0c500"),
                 bytes.fromhex("a4a1b0a100"), bytes.fromhex("b0a1090a0d00")]
        slots = {0xB0A1, 0xB3AA, 0xB0C5, 0xB0A2, 0xC5B0, 0xA4A1}
        for data in cases:
            expected = set()
            for start in range(len(data) - 1):
                code = int.from_bytes(data[start:start + 2], "big")
                if code not in slots:
                    continue
                end = data.find(b"\0", start)
                if end == -1:
                    continue
                try:
                    text = data[start:end].decode("cp949", errors="strict")
                except UnicodeDecodeError:
                    continue
                if is_printable_text(text):
                    expected.add((start, code, end))
            self.assertEqual(set(suffix_code_candidates(data, slots)), expected)

    def test_empty_font_set_has_no_raw_matches(self):
        self.assertEqual(raw_pair_hits(bytes.fromhex("b0a100"), set()), {})

    def test_single_character_candidate_is_kept_without_language_heuristic(self):
        data = "가".encode("cp949") + b"\0"
        self.assertEqual(len(list(printable_cstrings(data))), 1)
        self.assertEqual(list(suffix_code_candidates(data, {0xB0A1})), [(0, 0xB0A1, 2)])

    def test_suffix_validation_randomized_against_independent_decoder(self):
        randomizer = random.Random(20055)
        slots = {0xB0A1, 0xB3AA, 0xB0C5, 0xB0A2, 0xC5B0, 0xA4A1}
        tokens = [b"\0", b"\x01", b"\xff", b"A", b" ", b"\t", b"\x81",
                  *[code.to_bytes(2, "big") for code in slots]]
        for _ in range(300):
            data = b"".join(randomizer.choice(tokens) for _ in range(12)) + b"\0"
            expected = set()
            for start in range(len(data) - 1):
                code = int.from_bytes(data[start:start + 2], "big")
                if code not in slots:
                    continue
                end = data.find(b"\0", start)
                try:
                    text = data[start:end].decode("cp949", errors="strict")
                except UnicodeDecodeError:
                    continue
                if is_printable_text(text):
                    expected.add((start, code, end))
            self.assertEqual(set(suffix_code_candidates(data, slots)), expected)

    @staticmethod
    def elf_fixture():
        data = bytearray(88)
        data[:7] = b"\x7fELF\x01\x01\x01"
        struct.pack_into("<H", data, 18, 8)
        struct.pack_into("<I", data, 28, 52)
        struct.pack_into("<HH", data, 42, 32, 1)
        struct.pack_into("<8I", data, 52, 1, 84, 0x100000, 0x100000, 4, 8, 7, 4)
        data[84:] = b"AB\0\0"
        return data

    def test_elf_file_backed_load_segment(self):
        result = elf_load_segments(bytes(self.elf_fixture()))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["offset"], 84)
        self.assertEqual(result[0]["file_size"], 4)
        self.assertEqual(result[0]["memory_size"], 8)

    def test_elf_rejects_truncated_table_and_bad_architecture(self):
        data = self.elf_fixture()
        with self.assertRaises(ValueError):
            elf_load_segments(bytes(data[:70]))
        struct.pack_into("<H", data, 18, 3)
        with self.assertRaises(ValueError):
            elf_load_segments(bytes(data))

    def test_elf_rejects_out_of_bounds_segment_and_small_memory(self):
        data = self.elf_fixture()
        struct.pack_into("<I", data, 52 + 16, 5)
        with self.assertRaises(ValueError):
            elf_load_segments(bytes(data))
        data = self.elf_fixture()
        struct.pack_into("<I", data, 52 + 20, 3)
        with self.assertRaises(ValueError):
            elf_load_segments(bytes(data))

    def test_elf_rejects_missing_load_segments(self):
        data = self.elf_fixture()
        struct.pack_into("<I", data, 52, 0)
        with self.assertRaises(ValueError):
            elf_load_segments(bytes(data))


if __name__ == "__main__":
    unittest.main()
