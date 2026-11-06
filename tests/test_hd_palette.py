"""Explicit GS RGB5/TEXA expansion uses synthetic, redistribution-free TIM2."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools')]
from mysticnights.artwork import make_artwork_delta
from mysticnights.hd_artwork import build_texture
from mysticnights.hd_font import HdFontError, raw_atlas, tim2_replacement_identity
from mysticnights.resources import parse_res
from test_hd_font import textured_fixture
from test_resources import fixture as res_fixture


TEXA = {'ta0': 0, 'ta1': 128, 'aem': False}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def clut16_fixture(*, linear=False):
    width = height = 16
    data = bytearray(64 + width * height + 512)
    data[:8] = b'TIM2\x04\x00\x01\x00'
    struct.pack_into('<IIIHH4BHH', data, 16, len(data)-16,
                     512, 256, 48, 256, 0, 1, 0x81 if linear else 1, 5, width, height)
    struct.pack_into('<Q', data, 40, (19 << 20) | (4 << 26) | (4 << 30) | (2 << 51))
    data[64:320] = bytes([1]) * 256
    for index in range(256):
        physical = index if linear else ((index & ~0x18) | ((index & 8) << 1) | ((index & 16) >> 1))
        value = (index & 31) | ((index >> 3 & 31) << 5) | ((index >> 1 & 31) << 10)
        if index & 1: value |= 0x8000
        if index == 1: value = 0x801f
        struct.pack_into('<H', data, 320 + physical * 2, value)
    return bytes(data)


class HdPaletteTests(unittest.TestCase):
    def test_clut16_requires_explicit_typed_texa_and_no_guessed_aem(self):
        source = clut16_fixture()
        for texa in [None, {}, {'ta0': 0, 'ta1': 128}, dict(TEXA, other=1),
                     dict(TEXA, ta0=True), dict(TEXA, ta1=256), dict(TEXA, ta0=-1),
                     dict(TEXA, aem=0), dict(TEXA, aem=True)]:
            with self.subTest(texa=texa):
                with self.assertRaises(HdFontError):
                    tim2_replacement_identity(source, hash_function=lambda data: 1, clut16_texa=texa)
                with self.assertRaises(HdFontError): raw_atlas(source, clut16_texa=texa)

    def test_clut32_interface_unchanged_and_rejects_unused_texa(self):
        source = textured_fixture()
        self.assertEqual(tim2_replacement_identity(source, hash_function=lambda data: 1)['filename'], '1-1-00002213.png')
        self.assertEqual(raw_atlas(source).getpixel((0, 0)), (128,128,128,128))
        with self.assertRaisesRegex(HdFontError, 'non-CLUT16'):
            tim2_replacement_identity(source, clut16_texa=TEXA)

    def test_logical_16bit_clut_expands_by_shift_and_raw_texa_not_255_scale(self):
        calls = []
        def digest(data): calls.append(data); return len(calls)
        source = clut16_fixture()
        result = tim2_replacement_identity(source, hash_function=digest, clut16_texa=TEXA)
        self.assertEqual(result['filename'], '1-2-00001113.png')
        self.assertEqual([len(data) for data in calls], [256,1024])
        self.assertEqual(calls[1][:8], bytes([0,0,0,0,248,0,0,128]))
        self.assertEqual(result['clut16_texa'], TEXA)
        self.assertEqual(raw_atlas(source, clut16_texa=TEXA).getpixel((0, 0)), (248,0,0,128))
        # CSM1 and a deliberately linear stored CLUT select the same logical
        # colors; 5-bit white must be 248, never normalized/replicated 255.
        linear = clut16_fixture(linear=True)
        self.assertEqual(raw_atlas(source, clut16_texa=TEXA).tobytes(), raw_atlas(linear, clut16_texa=TEXA).tobytes())
        altered = dict(TEXA, ta0=31, ta1=201)
        self.assertEqual(raw_atlas(source, clut16_texa=altered).getpixel((0,0)), (248,0,0,201))

    def test_bad_clut16_layout_cpsm_and_mips_rejected(self):
        for change in [lambda b: b.__setitem__(33, 2),
                       lambda b: struct.pack_into('<I', b, 20, 1024),
                       lambda b: struct.pack_into('<Q', b, 40, (19<<20)|(4<<26)|(4<<30)),
                       lambda b: struct.pack_into('<Q', b, 40, (19<<20)|(4<<26)|(4<<30)|(2<<51)|(1<<55))]:
            data=bytearray(clut16_fixture()); change(data)
            with self.assertRaises(HdFontError):
                tim2_replacement_identity(bytes(data),hash_function=lambda data:1,clut16_texa=TEXA)

    def test_hd_artwork_propagates_texa_to_identity_base_and_png(self):
        source=clut16_fixture(); clean=bytearray(source);clean[64+1+16]=0
        row={'source_sha256':sha(source),
             'base_delta':make_artwork_delta(source,bytes(clean),[[1,1,1,1]],{'material':'clean'}),
             'clut16_texa':deepcopy(TEXA),'allowed_hd_rectangles':[[4,4,4,4]],
             'full_coverage_regions':[[4,4,4,4]],
             'layers':[{'id':'fresh','rect':[4,4,4,4],'mode':'replace-region','pixels_rle':[[16,[240,80,20,64]]]}]}
        image,proof=build_texture(source,row)
        self.assertEqual(image.getpixel((0,0)),(248,0,0,128))
        self.assertEqual(image.getpixel((4,4)),(240,80,20,64))
        self.assertEqual(proof['full_coverage_regions'],[[4,4,4,4]])
        with tempfile.TemporaryDirectory() as directory:
            import build_hd_artwork
            from mysticnights.texture_install import install_package,rollback_install
            root=Path(directory);resource=res_fixture({0:[('A.TM2',source)]});entry=parse_res(resource).get('A.TM2')
            row['reference']={'resource':'RES/SYSTEM.RES','member':'A.TM2','offset':entry.offset,'size':entry.size}
            path=root/'input.iso';path.write_bytes(b'fixture ISO identity');cnf=b'fixture serial'
            files={'RES/SYSTEM.RES':resource,'SYSTEM.CNF':cnf}
            fake=SimpleNamespace(path=path,size=path.stat().st_size,read=lambda name:files[name],
                                 get=lambda name:SimpleNamespace(offset=4096,size=len(files[name])))
            original={'size':fake.size,'sha256':'f'*64}
            manifest={'original':original,'modified':{'size':fake.size,'sha256':sha(path.read_bytes())},'locale':'test',
                      'changed_files':[{'path':'RES/SYSTEM.RES','offset':4096,'size':len(resource),'sha256':sha(resource)}]}
            version={'serial':'TEST-12345','iso':original,'files':{'SYSTEM.CNF':{'size':len(cnf),'sha256':sha(cnf)}}}
            recipe={'format':'hd-artwork-recipe','version':1,'scale':4,'serial':'TEST-12345','textures':[row]}
            (root/'assets').mkdir();(root/'assets/game-version.json').write_text(json.dumps(version),'utf8')
            m=root/'manifest.json';m.write_text(json.dumps(manifest),'utf8');r=root/'recipe.json';r.write_text(json.dumps(recipe),'utf8')
            with patch.object(build_hd_artwork,'ROOT',root),patch.object(build_hd_artwork,'IsoImage',return_value=fake):
                report=build_hd_artwork.build_pack(path,m,r,root/'pack',hash_function=lambda data:len(data))
            self.assertEqual(report['textures'][0]['clut16_texa'],TEXA)
            png=root/'pack'/report['textures'][0]['path']
            with Image.open(png) as reopened: self.assertEqual(reopened.tobytes(),image.tobytes())
            profile=root/'profile';(profile/'inis').mkdir(parents=True);(profile/'inis/PCSX2.ini').write_text('[Folders]\nTextures=textures\n','utf8')
            receipt=root/'receipt';self.assertEqual(install_package(root/'pack',profile,receipt)['state'],'installed')
            self.assertEqual(rollback_install(receipt)['state'],'rolled-back')


if __name__ == '__main__': unittest.main()
