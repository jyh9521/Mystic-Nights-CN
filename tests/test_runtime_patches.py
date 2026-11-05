import copy
import hashlib
import itertools
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from mysticnights.runtime_patches import (pcsx2_crc, address_offset, validate_recipe,
                                        patch_fixture, render_package, write_package)


class RuntimePatchTests(unittest.TestCase):
    def fixture(self):
        recipe = json.loads((ROOT / 'assets/runtime-patches.json').read_text('utf8'))
        data = bytearray(recipe['source_size'])
        data[:7] = b'\x7fELF\x01\x01\x01'
        struct.pack_into('<I', data, 28, 52)
        struct.pack_into('<HH', data, 42, 32, 1)
        struct.pack_into('<8I', data, 52, 1, 128, 0x100000, 0, 0x160000, 0x160000, 7, 128)
        for g in recipe['groups']:
            for w in g['writes']:
                offset = address_offset(data, int(w['address'], 16))
                struct.pack_into('<I', data, offset, int(w['before'], 16))
        source = bytes(data)
        recipe['source_sha256'] = hashlib.sha256(source).hexdigest()
        recipe['source_crc'] = pcsx2_crc(source)
        return source, recipe

    def test_all_sixteen_independent_combinations_round_trip(self):
        original, recipe = self.fixture()
        ids = [g['id'] for g in recipe['groups']]
        for flags in itertools.product((False, True), repeat=4):
            chosen = {k for k, enabled in zip(ids, flags) if enabled}
            modified = patch_fixture(original, original, recipe, chosen)
            self.assertEqual(patch_fixture(original, modified, recipe, chosen, reverse=True), original)
            for g in recipe['groups']:
                for w in g['writes']:
                    off = address_offset(original, int(w['address'], 16))
                    expected = w['after'] if g['id'] in chosen else w['before']
                    self.assertEqual(struct.unpack_from('<I', modified, off)[0], int(expected, 16))

    def test_identity_expected_words_overlap_and_unknown_groups_fail_closed(self):
        original, recipe = self.fixture()
        bad = bytearray(original); bad[-1] = 1
        with self.assertRaisesRegex(ValueError, 'identity'):
            validate_recipe(bytes(bad), original, recipe)
        bad = bytearray(original)
        off = address_offset(original, 0x16871C);bad[off] ^= 1
        with self.assertRaisesRegex(ValueError, 'anchor'):
            validate_recipe(original, bytes(bad), recipe)
        bad = bytearray(original);bad[24] ^= 1
        with self.assertRaisesRegex(ValueError, 'layout'):
            validate_recipe(original, bytes(bad), recipe)
        duplicate = copy.deepcopy(recipe)
        duplicate['groups'][1]['writes'].append(duplicate['groups'][0]['writes'][0])
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            validate_recipe(original, original, duplicate)
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            patch_fixture(original, original, recipe, {'unexpected'})
        with self.assertRaisesRegex(ValueError, 'rollback'):
            patch_fixture(original, original, recipe, {'infinite-ammo'}, reverse=True)

    def test_crc_is_little_endian_xor_not_crc32(self):
        self.assertEqual(pcsx2_crc(bytes.fromhex('0100000004030201')), '01020305')
        self.assertEqual(pcsx2_crc(b'\x01\x00\x00\x00\xff'), '00000001')

    def test_patch_and_cheat_packages_are_separate_and_crc_bound(self):
        original, recipe = self.fixture()
        current = bytearray(original);current[-4] ^= 1
        labels = json.loads((ROOT / 'locales/zh-CN/runtime-patches.json').read_text('utf8'))
        files, report = render_package(original, bytes(current), recipe, labels)
        self.assertEqual(len(files), 5)
        self.assertNotEqual(report['identities'][0]['crc'], report['identities'][1]['crc'])
        for role, data in [('original', original), ('localized', bytes(current))]:
            stem = f'{role}/{{kind}}/SCKA-20055_{pcsx2_crc(data)}.pnach'
            wide = files[stem.format(kind='patches')].decode('utf8')
            cheat = files[stem.format(kind='cheats')].decode('utf8')
            self.assertEqual(wide.count('patch=1'), 3)
            self.assertEqual(cheat.count('patch=1'), 7)
            self.assertIn('author=Arapapa', wide)
            self.assertNotIn('gsinterlacemode', wide)
            self.assertNotIn('gsaspectratio', cheat)
            self.assertEqual(cheat.count('\n['), 3)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'package'
            write_package(path, files)
            self.assertEqual({p.relative_to(path).as_posix(): p.read_bytes() for p in path.rglob('*') if p.is_file()}, files)
            with self.assertRaises(FileExistsError):write_package(path, files)


if __name__ == '__main__':
    unittest.main()
