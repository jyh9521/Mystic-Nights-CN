import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mysticnights.resources import MAGIC, ResourceError, parse_res


def fixture(groups=None):
    groups = groups or {0: [("A.TM2", b"abc")], 5: [("TEXT.SCR", b"SCR_TYPE DOC\r\n")]}
    result = bytearray(MAGIC)
    for group in range(8):
        members = groups.get(group, [])
        result += struct.pack("<I", len(members))
        for name, data in members:
            result += name.encode("cp949").ljust(32, b"\0")
            result += struct.pack("<I", len(data)) + data
    return bytes(result)


class ResourceTests(unittest.TestCase):
    def test_round_trip_and_unaligned_members(self):
        data = fixture()
        archive = parse_res(data)
        self.assertEqual(archive.group_counts, (1, 0, 0, 0, 0, 1, 0, 0))
        self.assertEqual(archive.read("A.TM2"), b"abc")
        self.assertNotEqual(archive.get("TEXT.SCR").offset % 4, 0)
        self.assertEqual(archive.replace({}), data)
        self.assertEqual(archive.replace({entry.key: archive.read(entry) for entry in archive.entries}), data)

    def test_equal_size_patch_changes_only_payload(self):
        data = fixture()
        archive = parse_res(data)
        result = archive.replace({"A.TM2": b"XYZ"})
        entry = archive.get("A.TM2")
        self.assertEqual(result[:entry.offset], data[:entry.offset])
        self.assertEqual(result[entry.end:], data[entry.end:])
        self.assertEqual(parse_res(result).read("A.TM2"), b"XYZ")

    def test_reject_resize(self):
        with self.assertRaises(ResourceError):
            parse_res(fixture()).replace({"A.TM2": b"toolong"})

    def test_reject_bad_inputs(self):
        data = fixture()
        for bad in [b"", b"2.00" + data[4:], data[:-1], data+b"\0"]:
            with self.subTest(length=len(bad)), self.assertRaises(ResourceError):
                parse_res(bad)
        bad_count = bytearray(data)
        struct.pack_into("<I", bad_count, 12, 0xFFFFFFFF)
        with self.assertRaises(ResourceError):
            parse_res(bad_count)
        bad_size = bytearray(data)
        struct.pack_into("<I", bad_size, 48, 0xFFFFFFFF)
        with self.assertRaises(ResourceError):
            parse_res(bad_size)

    def test_duplicate_name_requires_key(self):
        archive = parse_res(fixture({0: [("DUP", b"a"), ("DUP", b"b")]}))
        with self.assertRaises(ResourceError):
            archive.get("DUP")
        changed = parse_res(archive.replace({(0, 1): b"c"}))
        self.assertEqual(changed.read(changed.entries[1]), b"c")

    def test_duplicate_and_unknown_replacements(self):
        archive = parse_res(fixture())
        for replacements in ({"absent": b"x"}, {(7, 99): b"x"}, {"A.TM2": b"123", (0, 0): b"123"}):
            with self.assertRaises(ResourceError):
                archive.replace(replacements)


if __name__ == "__main__":
    unittest.main()
