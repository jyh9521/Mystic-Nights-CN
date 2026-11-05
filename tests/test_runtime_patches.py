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
sys.path.insert(0, str(ROOT / 'tools'))
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
        # Scalar input/clamp fragments for a synthetic executable; no external
        # retail file is required by these instruction replay regression tests.
        positive = [0x84430860,0x2862FFA6,0x1440011D,0,0x2861005B,0x1420000F,0,
                    0x14C0000D,0,0xC6020208,0x3C023F00,0x44820800,0,0x46011040,
                    0x46040836,0x45010005,0xE6010208,0x46032034,0x45000002,0,0xE6040208]
        negative = [0xC6020208,0x3C023F00,0x44820800,0,0x46011041,0xE6010208,
                    0xC6020214,0xC6010208,0x46020834,0x4500FEEB,0,0x1000FEE9,0xE6020208]
        for start, words in ((0x16A2C4,positive),(0x16A744,negative)):
            for index,value in enumerate(words):
                struct.pack_into('<I',data,address_offset(data,start+index*4),value)
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
            self.assertEqual(cheat.count('patch=1'), 10)
            self.assertIn('author=Arapapa', wide)
            self.assertNotIn('gsinterlacemode', wide)
            self.assertNotIn('gsaspectratio', cheat)
            self.assertEqual(cheat.count('\n['), 3)
            self.assertIn('[反转右摇杆水平视角]',cheat)
            self.assertIn('左右和上下',cheat)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'package'
            write_package(path, files)
            self.assertEqual({p.relative_to(path).as_posix(): p.read_bytes() for p in path.rglob('*') if p.is_file()}, files)
            with self.assertRaises(FileExistsError):write_package(path, files)

    def test_vertical_negation_preserves_actual_gates_clamps_and_delay_stores(self):
        from verify_runtime_patches import replay_vertical_input
        original,recipe=self.fixture()
        modified=patch_fixture(original,original,recipe,{'right-stick-horizontal'})
        before=replay_vertical_input(original,127,-5.,upper=0.,lower=-10.)
        self.assertEqual(before,-4.5)
        self.assertEqual(replay_vertical_input(modified,127,-5.,upper=0.,lower=-10.),-5.5)
        for axis in (-128,-91,-90,-1,0,1,90,91,127):
            for lower,upper in ((-10.,0.),(-5.,-1.),(-1.,2.)):
                for height in (lower-.5,lower,lower+.25,(lower+upper)/2,upper-.25,upper,upper+.5):
                    for inhibited in (False,True):
                        self.assertEqual(replay_vertical_input(modified,axis,height,upper=upper,lower=lower,inhibited=inhibited),
                                         replay_vertical_input(original,-axis,height,upper=upper,lower=lower,inhibited=inhibited))
        # Retain the source's conditional clamp exactly, including its asymmetric
        # overshoot when the original upper limit is nonnegative.
        self.assertEqual(replay_vertical_input(modified,127,-10.,upper=0.,lower=-10.),-10.)
        self.assertEqual(replay_vertical_input(modified,-128,2.,upper=-1.,lower=-5.),-1.)
        self.assertEqual(replay_vertical_input(modified,-128,2.,upper=2.,lower=-1.),2.5)
        self.assertEqual(replay_vertical_input(modified,-128,-5.,upper=0.,lower=-10.,inhibited=True),-5.)
        self.assertEqual(patch_fixture(original,modified,recipe,{'right-stick-horizontal'},reverse=True),original)


if __name__ == '__main__':
    unittest.main()
