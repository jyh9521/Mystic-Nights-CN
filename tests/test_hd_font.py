"""Optional HD font tests use original synthetic outlines and TIM2 fixtures."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mysticnights.font import FontError, build_font
from mysticnights.hd_font import (
    HdFontError, build_hd_atlases, format_replacement_name, indexed_hash_payload,
    raw_atlas, replacement_bits, swizzle8_offset, tim2_replacement_identity, validate_inputs,
)
from test_font import fnt_fixture, tim2_fixture
from test_network_font import make_outline


def textured_fixture():
    data = bytearray(tim2_fixture())
    struct.pack_into("<Q", data, 40, (19 << 20) | (8 << 26) | (8 << 30))
    return bytes(data)


class HdFontTests(unittest.TestCase):
    def test_psmt8_offsets_are_permutation_and_reference_points(self):
        self.assertEqual(sorted(swizzle8_offset(x, y) for y in range(16) for x in range(16)), list(range(256)))
        for xy, expected in { (0, 0): 0, (1, 0): 4, (4, 2): 1, (0, 2): 33, (0, 4): 96, (15, 15): 255 }.items():
            self.assertEqual(swizzle8_offset(*xy), expected)
        for xy in ((16, 0), (-1, 0), (0, 16)):
            with self.assertRaises(HdFontError):
                swizzle8_offset(*xy)

    def test_hash_payload_uses_logical_block_order_not_linear_pixels(self):
        pixels = bytes((x + 3*y) % 256 for y in range(32) for x in range(32))
        payload = indexed_hash_payload(pixels, 32, 32)
        self.assertEqual(len(payload), 1024)
        for by in range(2):
            for bx in range(2):
                for y in range(16):
                    for x in range(16):
                        self.assertEqual(payload[(by*2+bx)*256 + swizzle8_offset(x,y)], pixels[(by*16+y)*32+bx*16+x])
        self.assertNotEqual(payload, pixels)
        for args in ((pixels[:-1],32,32),(pixels,31,32),(b"",0,0)):
            with self.assertRaises(HdFontError):
                indexed_hash_payload(*args)

    def test_filename_has_exact_palette_hash_and_tex0_bits(self):
        self.assertEqual(replacement_bits(19, 8, 8), 0x2213)
        self.assertEqual(format_replacement_name(0x123, 0x456, 0x2213), "123-456-00002213.png")
        for args in ((-1,1,0),(1,1,1<<32)):
            with self.assertRaises(HdFontError):
                format_replacement_name(*args)

    def test_tim2_hash_identity_hashes_native_pixels_and_logical_clut(self):
        calls=[]
        def digest(data):
            calls.append(data)
            return len(calls)
        result=tim2_replacement_identity(textured_fixture(),hash_function=digest)
        self.assertEqual(result["filename"],"1-2-00002213.png")
        self.assertEqual((len(calls[0]),len(calls[1])),(65536,1024))
        self.assertEqual(calls[1][-4:],bytes([128,128,128,128]))
        data=bytearray(16+48+512*256+1024)
        data[:64]=textured_fixture()[:64]
        struct.pack_into("<III",data,16,len(data)-16,1024,512*256)
        struct.pack_into("<HHQ",data,36,512,256,(19<<20)|(9<<26)|(8<<30))
        result=tim2_replacement_identity(bytes(data),hash_function=lambda data:1)
        self.assertEqual(result["bits"],"00002253")

    def test_raw_atlas_does_not_double_alpha(self):
        image = raw_atlas(textured_fixture())
        self.assertEqual(image.getpixel((0,0)), (128,128,128,128))

    def test_new_outline_at_4x_keeps_native_layout_and_protected_pixels(self):
        with tempfile.TemporaryDirectory() as directory:
            font = Path(directory) / "synthetic.ttf"
            digest = make_outline(font)
            mapping={"中":0xA4A1,"文":0xA4A2}
            original=build_font(fnt_fixture(),{"FONT_8.TM2":textured_fixture()},[],font,digest,pixel_size=12,existing_mapping=mapping).textures
            result = build_hd_atlases(fnt_fixture(), original, mapping, font.read_bytes(), digest, pixel_size=12)
            self.assertEqual(result.baseline_shift, 0)
            self.assertEqual(result.mapped_glyphs, 2)
            image = result.images["FONT_8.TM2"]
            self.assertEqual(image.size, (1024,1024))
            native = raw_atlas(original["FONT_8.TM2"]).resize(image.size, Image.Resampling.NEAREST)
            # ASCII slot, unmapped source pixels, and atlas padding remain exact.
            self.assertEqual(image.crop((4,0,24,56)).tobytes(), native.crop((4,0,24,56)).tobytes())
            self.assertEqual(image.crop((0,60,1024,1024)).tobytes(), native.crop((0,60,1024,1024)).tobytes())
            self.assertEqual(image.crop((32,0,84,4)).getbbox(), None)
            self.assertLessEqual(max(image.crop((32,4,84,56)).getchannel("A").tobytes()), 128)
            # Fresh outline edges have sub-native structure, not 4x nearest cells.
            self.assertTrue(any(len({image.getpixel((x+i,y+j)) for i in range(4) for j in range(4)})>1
                                for y in range(4,56,4) for x in range(32,84,4)))
            corrupt=bytearray(original["FONT_8.TM2"]); corrupt[64+8]=255
            with self.assertRaisesRegex(HdFontError,"manifest mapping/raster"):
                build_hd_atlases(fnt_fixture(),{"FONT_8.TM2":bytes(corrupt)},mapping,font.read_bytes(),digest,pixel_size=12)
            overlapping=bytearray(fnt_fixture()); struct.pack_into("<H",overlapping,10,10)
            with self.assertRaisesRegex(HdFontError,"protected glyph"):
                build_hd_atlases(bytes(overlapping),original,mapping,font.read_bytes(),digest,pixel_size=12)

    def test_outline_guards_and_existing_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            font = Path(directory) / "synthetic.ttf"
            digest = make_outline(font)
            args = (fnt_fixture(), {"FONT_8.TM2": textured_fixture()})
            for mapping in ({"中":0x41}, {"中":0xA4A1,"文":0xA4A1}, {"新":0xA4A1}):
                with self.assertRaises((HdFontError,FontError)):
                    build_hd_atlases(*args,mapping,font.read_bytes(),digest,pixel_size=12)
            with self.assertRaisesRegex(HdFontError,"SHA-256"):
                build_hd_atlases(*args,{"中":0xA4A1},font.read_bytes(),"0"*64,pixel_size=12)
            with self.assertRaises((HdFontError,FontError)):
                build_hd_atlases(*args,{"中":0xA4A1},font.read_bytes(),digest,pixel_size=60)

    def test_supported_font_tex0_is_checked_not_guessed(self):
        with tempfile.TemporaryDirectory() as directory:
            font=Path(directory)/"synthetic.ttf"
            digest=make_outline(font)
            with self.assertRaisesRegex(HdFontError,"TEX0"):
                build_hd_atlases(fnt_fixture(),{"FONT_8.TM2":tim2_fixture()},{"中":0xA4A1},font.read_bytes(),digest,pixel_size=12)

    def test_identity_binds_iso_manifest_font_and_system_container(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/"tiny.iso"; p.write_bytes(b"synthetic ISO")
            font=b"synthetic font"; system=b"synthetic system"; cnf=b"synthetic cnf"
            sha=lambda b:hashlib.sha256(b).hexdigest()
            spec={"iso":{"size":99,"sha256":"f"*64},"serial":"SCKA-20055","files":{"SYSTEM.CNF":{"size":len(cnf),"sha256":sha(cnf)}}}
            manifest={"original":dict(spec["iso"]),"modified":{"size":p.stat().st_size,"sha256":sha(p.read_bytes())},
                      "font":{"sha256":sha(font),"pixel_size":12,"mapping":{"中":0xA4A1}},
                      "changed_files":[{"path":"RES/SYSTEM.RES","size":len(system),"sha256":sha(system)}]}
            validate_inputs(p,manifest,font,{"sha256":sha(font)},spec,system,cnf)
            bad=json.loads(json.dumps(manifest)); bad["modified"]["sha256"]="0"*64
            with self.assertRaisesRegex(HdFontError,"ISO"):
                validate_inputs(p,bad,font,{"sha256":sha(font)},spec,system,cnf)
            with self.assertRaisesRegex(HdFontError,"SYSTEM.RES"):
                validate_inputs(p,manifest,font,{"sha256":sha(font)},spec,system+b"!",cnf)
            with self.assertRaisesRegex(HdFontError,"font"):
                validate_inputs(p,manifest,font+b"!",{"sha256":sha(font)},spec,system,cnf)


if __name__ == "__main__":
    unittest.main()
