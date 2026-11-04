"""Synthetic ISO9660 tests; no commercial game bytes are fixtures."""

import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mysticnights.iso9660 import IsoError, IsoImage, SECTOR_SIZE, replace_files


def dual(value, width):
    return value.to_bytes(width, "little") + value.to_bytes(width, "big")


def record(name, lba, size, *, directory=False):
    result = bytearray(33 + len(name) + (len(name) % 2 == 0))
    result[0] = len(result)
    result[2:10] = dual(lba, 4)
    result[10:18] = dual(size, 4)
    result[25] = 2 if directory else 0
    result[28:32] = dual(1, 2)
    result[32] = len(name)
    result[33:33 + len(name)] = name
    return result


def synthetic_iso():
    result = bytearray(26 * SECTOR_SIZE)
    pvd = bytearray(SECTOR_SIZE)
    pvd[:7] = b"\x01CD001\x01"
    pvd[40:72] = b"SYNTHETIC".ljust(32, b" ")
    pvd[80:88] = dual(26, 4)
    pvd[120:124] = dual(1, 2)
    pvd[124:128] = dual(1, 2)
    pvd[128:132] = dual(SECTOR_SIZE, 2)
    pvd[132:140] = dual(10, 4)
    pvd[140:144] = (18).to_bytes(4, "little")
    pvd[148:152] = (19).to_bytes(4, "big")
    pvd[156:190] = record(b"\x00", 20, SECTOR_SIZE, directory=True)
    result[16 * SECTOR_SIZE:17 * SECTOR_SIZE] = pvd
    result[17 * SECTOR_SIZE:17 * SECTOR_SIZE + 7] = b"\xffCD001\x01"
    root = b"".join((record(b"\x00", 20, SECTOR_SIZE, directory=True),
                     record(b"\x01", 20, SECTOR_SIZE, directory=True),
                     record(b"RES", 21, SECTOR_SIZE, directory=True),
                     record(b"MAIN.BIN;1", 22, 9)))
    child = b"".join((record(b"\x00", 21, SECTOR_SIZE, directory=True),
                      record(b"\x01", 20, SECTOR_SIZE, directory=True),
                      record(b"SYSTEM.RES;1", 23, 7)))
    result[20 * SECTOR_SIZE:20 * SECTOR_SIZE + len(root)] = root
    result[21 * SECTOR_SIZE:21 * SECTOR_SIZE + len(child)] = child
    result[22 * SECTOR_SIZE:22 * SECTOR_SIZE + 9] = b"baseline!"
    result[23 * SECTOR_SIZE:23 * SECTOR_SIZE + 7] = b"system!"
    return result


class IsoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "original.iso"
        self.original = bytes(synthetic_iso())
        self.source.write_bytes(self.original)
        self.digest = hashlib.sha256(self.original).hexdigest()

    def test_inventory_and_read(self):
        image = IsoImage(self.source)
        self.assertEqual(image.volume_id, "SYNTHETIC")
        self.assertEqual(set(image.files), {"MAIN.BIN", "RES/SYSTEM.RES"})
        self.assertEqual(set(image.directories), {"", "RES"})
        self.assertEqual(image.get("RES/SYSTEM.RES").offset, 23 * SECTOR_SIZE)
        self.assertEqual(image.read("/RES\\SYSTEM.RES;1"), b"system!")

    def test_same_length_copy_only_changes_intended_bytes(self):
        out = self.root / "modified.iso"
        result = replace_files(self.source, out, {"MAIN.BIN": b"modified!"}, expected_sha256=self.digest, expected_size=len(self.original))
        expected = bytearray(self.original)
        expected[22 * SECTOR_SIZE:22 * SECTOR_SIZE + 9] = b"modified!"
        self.assertEqual(out.read_bytes(), expected)
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(result["sha256"], hashlib.sha256(expected).hexdigest())
        self.assertEqual(IsoImage(out).read("MAIN.BIN"), b"modified!")

    def test_noop_copy_is_byte_identical(self):
        out = self.root / "copy.iso"
        result = replace_files(self.source, out, {}, expected_sha256=self.digest)
        self.assertEqual(result["sha256"], self.digest)
        self.assertEqual(out.read_bytes(), self.original)

    def test_path_payload(self):
        payload = self.root / "replacement.dat"
        payload.write_bytes(b"changed")
        out = self.root / "modified.iso"
        replace_files(self.source, out, {"RES/SYSTEM.RES": payload}, expected_sha256=self.digest)
        self.assertEqual(IsoImage(out).read("RES/SYSTEM.RES"), b"changed")

    def test_wrong_source_hash_fails_before_output_creation(self):
        out = self.root / "modified.iso"
        with self.assertRaisesRegex(IsoError, "SHA-256"):
            replace_files(self.source, out, {}, expected_sha256="0" * 64)
        self.assertFalse(out.exists())

    def test_wrong_source_size_fails_before_output_creation(self):
        out = self.root / "modified.iso"
        with self.assertRaisesRegex(IsoError, "size"):
            replace_files(self.source, out, {}, expected_sha256=self.digest, expected_size=1)
        self.assertFalse(out.exists())

    def test_rejects_growth_and_shrink(self):
        for payload in (b"short", b"too long a replacement"):
            with self.subTest(payload=payload):
                out = self.root / "modified.iso"
                with self.assertRaisesRegex(IsoError, "size differs"):
                    replace_files(self.source, out, {"MAIN.BIN": payload}, expected_sha256=self.digest)
                self.assertFalse(out.exists())

    def test_rejects_unknown_file(self):
        out = self.root / "modified.iso"
        with self.assertRaises(KeyError):
            replace_files(self.source, out, {"MISSING": b"x"}, expected_sha256=self.digest)
        self.assertFalse(out.exists())

    def test_rejects_alias_duplicate_replacement(self):
        with self.assertRaisesRegex(IsoError, "twice"):
            replace_files(self.source, self.root / "out.iso", {"MAIN.BIN": b"modified!", "/MAIN.BIN;1": b"modified!"}, expected_sha256=self.digest)

    def test_rejects_in_place_or_existing_output(self):
        with self.assertRaises(FileExistsError):
            replace_files(self.source, self.source, {}, expected_sha256=self.digest)
        out = self.root / "exists.iso"
        out.write_bytes(b"keep")
        with self.assertRaises(FileExistsError):
            replace_files(self.source, out, {}, expected_sha256=self.digest)
        self.assertEqual(out.read_bytes(), b"keep")

    def corrupt(self, offset, payload):
        data = bytearray(self.original)
        data[offset:offset + len(payload)] = payload
        self.source.write_bytes(data)

    def test_rejects_endian_disagreement(self):
        self.corrupt(16 * SECTOR_SIZE + 84, b"\x00\x00\x00\x01")
        with self.assertRaisesRegex(IsoError, "Endian"):
            IsoImage(self.source)

    def test_rejects_bad_signature(self):
        self.corrupt(16 * SECTOR_SIZE + 1, b"BROKE")
        with self.assertRaisesRegex(IsoError, "descriptor"):
            IsoImage(self.source)

    def test_rejects_truncated_image(self):
        self.source.write_bytes(self.original[:-1])
        with self.assertRaises(IsoError):
            IsoImage(self.source)

    def test_rejects_extent_outside_image(self):
        location = IsoImage(self.source).get("MAIN.BIN").record_offset
        self.corrupt(location + 2, dual(99, 4))
        with self.assertRaisesRegex(IsoError, "outside"):
            IsoImage(self.source)

    def test_rejects_multi_extent(self):
        location = IsoImage(self.source).get("MAIN.BIN").record_offset
        self.corrupt(location + 25, b"\x80")
        with self.assertRaisesRegex(IsoError, "Multi-extent"):
            IsoImage(self.source)

    def test_rejects_interleaving(self):
        location = IsoImage(self.source).get("MAIN.BIN").record_offset
        self.corrupt(location + 26, b"\x01")
        with self.assertRaisesRegex(IsoError, "interleaved"):
            IsoImage(self.source)

    def test_rejects_file_overlapping_metadata(self):
        location = IsoImage(self.source).get("MAIN.BIN").record_offset
        self.corrupt(location + 2, dual(20, 4))
        with self.assertRaisesRegex(IsoError, "overlaps filesystem metadata"):
            IsoImage(self.source)

    def test_rejects_replacement_overlapping_another_file(self):
        location = IsoImage(self.source).get("MAIN.BIN").record_offset
        self.corrupt(location + 2, dual(23, 4))
        digest = hashlib.sha256(self.source.read_bytes()).hexdigest()
        with self.assertRaisesRegex(IsoError, "overlaps another file"):
            replace_files(self.source, self.root / "out.iso", {"MAIN.BIN": b"modified!"}, expected_sha256=digest)

    def test_rejects_invalid_parent_entry(self):
        self.corrupt(21 * SECTOR_SIZE + 34 + 2, dual(21, 4))
        with self.assertRaisesRegex(IsoError, "current/parent"):
            IsoImage(self.source)

    def test_rejects_nonzero_sector_padding(self):
        self.corrupt(20 * SECTOR_SIZE + 1000, b"bad")
        with self.assertRaisesRegex(IsoError, "padding"):
            IsoImage(self.source)


if __name__ == "__main__":
    unittest.main()
