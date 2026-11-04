"""Synthetic icon.sys fixtures; no original game assets are test dependencies."""
import copy
import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mysticnights.save_metadata import (ICON_SYS_SIZE, TITLE_OFFSET, TITLE_CAPACITY,
                                      RESOURCE, TITLE_ID, parse_icon_sys,
                                      patch_icon_sys, build_save_metadata)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fixture(title="Network title"):
    # Preserve conspicuous nonzero unknown bytes to exercise edit isolation.
    data = bytearray((i * 43 + 7) % 256 for i in range(ICON_SYS_SIZE))
    data[:4] = b"PS2D"
    struct.pack_into("<HH", data, 4, 4, 4)
    data[TITLE_OFFSET:TITLE_OFFSET + TITLE_CAPACITY] = title.encode("cp932").ljust(TITLE_CAPACITY, b"\0")
    for offset in (0x104, 0x144, 0x184):
        data[offset:offset + 64] = b"TEST.ICO".ljust(64, b"\0")
    data = bytes(data)
    field_hash = digest(data[TITLE_OFFSET:TITLE_OFFSET + TITLE_CAPACITY])
    definition = {"resource": RESOURCE, "format": "ps2-icon-sys", "size": ICON_SYS_SIZE,
                  "sha256": digest(data), "expected_type": 4, "expected_nl_offset": 4,
                  "expected_icon_filenames": ["TEST.ICO"] * 3,
                  "title": {"id": TITLE_ID, "offset": TITLE_OFFSET, "capacity": TITLE_CAPACITY,
                            "source": title, "source_sha256": field_hash}}
    translation = {"id": TITLE_ID, "source": title, "source_sha256": field_hash,
                   "target": "通信配置", "encoding": "cp932", "line_break_after": 4, "status": "draft"}
    return data, definition, translation


class IconSysTests(unittest.TestCase):
    def test_parses_original_title_and_byte_offset(self):
        data, _, _ = fixture()
        parsed = parse_icon_sys(data)
        self.assertEqual(parsed.title, "Network title")
        self.assertEqual(parsed.title_lines, ("Netw", "ork title"))
        self.assertEqual(parsed.nl_offset, 4)
        self.assertEqual(parsed.filenames, ("TEST.ICO",) * 3)

    def test_exact_encoding_readback_and_isolation(self):
        data, definition, translation = fixture()
        result = patch_icon_sys(data, definition, translation)
        self.assertEqual(len(result), len(data))
        parsed = parse_icon_sys(result)
        self.assertEqual(parsed.title_bytes.hex(), "92ca904d947a9275")
        self.assertEqual(parsed.title_lines, ("通信配置", ""))
        self.assertEqual(parsed.nl_offset, 8)
        allowed = {6, 7} | set(range(TITLE_OFFSET, TITLE_OFFSET + TITLE_CAPACITY))
        self.assertTrue(all(a == b or i in allowed for i, (a, b) in enumerate(zip(data, result))))
        self.assertEqual(data, fixture()[0])

    def test_fullwidth_space_in_source_is_printable_metadata(self):
        data, definition, translation = fixture("Ｎ　Ｔ")
        self.assertEqual(parse_icon_sys(data).title_lines, ("Ｎ　", "Ｔ"))
        self.assertEqual(parse_icon_sys(patch_icon_sys(data, definition, translation)).title, "通信配置")

    def test_multibyte_line_break_uses_encoded_prefix(self):
        data, definition, translation = fixture()
        translation.update(target="A通信B", line_break_after=2)
        parsed = parse_icon_sys(patch_icon_sys(data, definition, translation))
        self.assertEqual(parsed.nl_offset, 3)
        self.assertEqual(parsed.title_lines, ("A通", "信B"))

    def test_same_title_is_byte_identical(self):
        data, definition, translation = fixture()
        translation.update(target=definition["title"]["source"], line_break_after=4)
        self.assertEqual(patch_icon_sys(data, definition, translation), data)

    def test_rollback_spans_restore_original_digest(self):
        data, definition, translation = fixture()
        restored = bytearray(patch_icon_sys(data, definition, translation))
        for start, end in ((6, 8), (TITLE_OFFSET, TITLE_OFFSET + TITLE_CAPACITY)):
            restored[start:end] = data[start:end]
        self.assertEqual(digest(restored), digest(data))
        self.assertEqual(parse_icon_sys(restored), parse_icon_sys(data))

    def test_invalid_layout_size_magic_or_padding_rejected(self):
        data, _, _ = fixture()
        for changed in (data[:-1], data + b"\0", b"BAD!" + data[4:]):
            with self.assertRaises(ValueError):
                parse_icon_sys(changed)
        for offset in (TITLE_OFFSET + 20, 0x104 + 20):
            changed = bytearray(data)
            changed[offset] = 1
            with self.assertRaisesRegex(ValueError, "padding"):
                parse_icon_sys(changed)

    def test_unterminated_invalid_encoding_and_control_rejected(self):
        data, _, _ = fixture()
        for field in (b"A" * TITLE_CAPACITY, b"\x81\0", b"A\nB\0"):
            changed = bytearray(data)
            changed[TITLE_OFFSET:TITLE_OFFSET + TITLE_CAPACITY] = field.ljust(TITLE_CAPACITY, b"\0")
            with self.assertRaises(ValueError):
                parse_icon_sys(changed)

    def test_source_newline_must_be_valid_byte_boundary(self):
        data, definition, translation = fixture()
        changed = bytearray(patch_icon_sys(data, definition, translation))
        for nl_offset in (1, 3, 9, 65535):
            struct.pack_into("<H", changed, 6, nl_offset)
            with self.assertRaises(ValueError):
                parse_icon_sys(changed)

    def test_source_hash_size_and_schema_guards(self):
        data, definition, translation = fixture()
        changes = ({"sha256": "0" * 64}, {"size": 963}, {"resource": "SCKA_200.55"},
                   {"format": "anything"}, {"expected_type": 5}, {"expected_nl_offset": 0},
                   {"expected_icon_filenames": ["OTHER.ICO"] * 3})
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                patch_icon_sys(data, {**definition, **change}, translation)
        changed = bytearray(data)
        changed[100] ^= 1
        with self.assertRaisesRegex(ValueError, "hash"):
            patch_icon_sys(changed, definition, translation)

    def test_title_slot_metadata_guards(self):
        data, definition, translation = fixture()
        for change in ({"offset": 191}, {"capacity": 70}, {"source": "Other"},
                       {"source_sha256": "0" * 64}, {"id": "Unknown"}):
            d = copy.deepcopy(definition)
            d["title"].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                patch_icon_sys(data, d, translation)

    def test_translation_source_status_encoding_guards(self):
        data, definition, translation = fixture()
        for change in ({"id": "SCKA_200.55@00152718"}, {"source": "Wrong"},
                       {"source_sha256": "0" * 64}, {"encoding": "cp949"}, {"status": "untranslated"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                patch_icon_sys(data, definition, {**translation, **change})

    def test_invalid_targets_and_character_splits_rejected(self):
        data, definition, translation = fixture()
        for target in ("", " ", "诡秘之夜", "A\0B", "A\nB", "A" * 68, "〜"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                patch_icon_sys(data, definition, {**translation, "target": target, "line_break_after": len(target)})
        for split in (-1, 5, 1.0, True, None):
            with self.subTest(split=split), self.assertRaises(ValueError):
                patch_icon_sys(data, definition, {**translation, "line_break_after": split})

    def test_exact_capacity_includes_nul(self):
        data, definition, translation = fixture()
        result = patch_icon_sys(data, definition, {**translation, "target": "A" * 67, "line_break_after": 67})
        self.assertEqual(result[TITLE_OFFSET + 67], 0)
        self.assertEqual(len(parse_icon_sys(result).title_bytes), 67)

    def test_filename_paths_rejected(self):
        data, _, _ = fixture()
        changed = bytearray(data)
        changed[0x104:0x144] = b"../TEST.ICO".ljust(64, b"\0")
        with self.assertRaisesRegex(ValueError, "filename"):
            parse_icon_sys(changed)


class BuildSaveMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        data, self.definition, self.translation = fixture()
        path = Path(self.temp.name) / "synthetic-disc.bin"
        path.write_bytes(b"synthetic-disc-v1")
        class Image:
            def read(_, resource):
                if resource != RESOURCE:
                    raise AssertionError("Unexpected resource read")
                return data
        self.image = Image()
        self.image.path = path
        self.recipe = {"format": "save-metadata-slots", "version": 1,
                       "original_iso_sha256": digest(path.read_bytes()), "sources": [self.definition]}
        self.catalogue = {"format": "save-metadata-catalogue", "version": 1, "locale": "sample",
                          "original_iso_sha256": self.recipe["original_iso_sha256"], "entries": [self.translation]}

    def test_build_is_read_only_and_locale_neutral(self):
        result = build_save_metadata(self.image, self.recipe, self.catalogue)
        self.assertEqual(list(result), [RESOURCE])
        self.assertEqual(parse_icon_sys(result[RESOURCE]).title, "通信配置")
        self.assertEqual(self.image.path.read_bytes(), b"synthetic-disc-v1")

    def test_wrong_original_disc_or_recipe_rejected(self):
        self.image.path.write_bytes(b"different-disc-v1")
        with self.assertRaisesRegex(ValueError, "ISO hash"):
            build_save_metadata(self.image, self.recipe, self.catalogue)

    def test_invalid_catalogue_or_source_count_rejected(self):
        for side, changes in (("recipe", {"version": 2}), ("recipe", {"sources": []}),
                              ("recipe", {"sources": [self.definition] * 2}),
                              ("catalogue", {"entries": [self.translation] * 2}),
                              ("catalogue", {"original_iso_sha256": "0" * 64}),
                              ("catalogue", {"locale": ""})):
            recipe, catalogue = copy.deepcopy(self.recipe), copy.deepcopy(self.catalogue)
            (recipe if side == "recipe" else catalogue).update(changes)
            with self.subTest(side=side, changes=changes), self.assertRaises(ValueError):
                build_save_metadata(self.image, recipe, catalogue)


if __name__ == "__main__":
    unittest.main()
