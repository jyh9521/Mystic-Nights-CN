"""Synthetic assets only: no game, retail texture or downloaded font needed."""
from copy import deepcopy
import hashlib
from io import BytesIO
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mysticnights.graphics import decode_tim2, patch_texture, build_graphics, _rect_bytes
from mysticnights.resources import MAGIC, parse_res


def digest(data):
    return hashlib.sha256(data).hexdigest()


def font_fixture():
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder([".notdef", "space", "A", "B"])
    fb.setupCharacterMap({32: "space", 65: "A", 66: "B"})
    glyphs = {}
    for name in [".notdef", "space", "A", "B"]:
        p = TTGlyphPen(None)
        if name != "space":
            p.moveTo((50, 0)); p.lineTo((550, 0)); p.lineTo((550, 700)); p.lineTo((50, 700)); p.closePath()
        glyphs[name] = p.glyph()
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({name: (600, 0) for name in glyphs})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "Synthetic", "styleName": "Regular", "uniqueFontIdentifier": "Synthetic", "fullName": "Synthetic", "psName": "Synthetic"})
    fb.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    fb.setupPost(); fb.setupMaxp()
    stream = BytesIO(); fb.save(stream)
    return stream.getvalue()


def tim2_fixture(clut=3):
    width, height = 32, 24
    pixels = bytearray(width * height)
    for y in range(8, 14):
        for x in range(12, 18):
            pixels[y * width + x] = 1
    stride = 4 if clut == 3 else 2
    palette = bytearray(256 * stride)
    for idx in range(256):
        if stride == 4:
            palette[idx * 4:idx * 4 + 4] = bytes([0, 0, 0, 128])
        else:
            struct.pack_into("<H", palette, idx * 2, 0x8000)
    palette[stride:2 * stride] = bytes([255, 255, 255, 128]) if stride == 4 else b"\xff\xff"
    header = bytearray(64)
    header[:8] = b"TIM2\x04\x00\x01\x00"
    struct.pack_into("<IIIHHBBBBHH", header, 16, 48 + len(pixels) + len(palette), len(palette), len(pixels), 48, 256, 0, 1, clut, 5, width, height)
    return bytes(header + pixels + palette)


def res_fixture(texture):
    out = bytearray(MAGIC)
    for group in range(8):
        fields = [("A.TM2", texture), ("TEXT.SCR", b"before")] if group == 0 else []
        out += struct.pack("<I", len(fields))
        for name, value in fields:
            out += name.encode().ljust(32, b"\0") + struct.pack("<I", len(value)) + value
    return bytes(out)


class GraphicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.font = font_fixture()

    def setUp(self):
        self.source = tim2_fixture()
        _, info = decode_tim2(self.source)
        self.recipe = {"sha256": digest(self.source), "profile": [32, 24, 5, 3], "slots": [{
            "id": "label", "install": True, "rect": [4, 4, 24, 16],
            "source_pixels_sha256": digest(_rect_bytes(self.source, info, [4, 4, 24, 16])),
            "background_index": 0, "foreground_rgba": [255, 255, 255, 255],
            "font_size": 12, "minimum_font_size": 10}]}

    def apply(self, recipe=None, target="A"):
        return patch_texture(self.source, recipe or self.recipe, {"label": target}, self.font)

    def test_decoder_profiles_and_csm1_palette_order(self):
        for clut in [1, 3]:
            im, info = decode_tim2(tim2_fixture(clut))
            self.assertEqual(im.getpixel((12, 8)), (255, 255, 255, 255))
            self.assertEqual(im.getpixel((0, 0)), (0, 0, 0, 255))
            self.assertEqual(info["pixel_size"], 768)
        data = bytearray(self.source)
        data[64] = 8
        data[64 + 768 + 16 * 4:64 + 768 + 16 * 4 + 4] = bytes([1, 2, 3, 64])
        self.assertEqual(decode_tim2(bytes(data))[0].getpixel((0, 0)), (1, 2, 3, 127))

    def test_decoder_rejects_unknown_and_truncated_formats(self):
        for bad in [b"", self.source[:-1], self.source + b"x", b"nope" + self.source[4:]]:
            with self.assertRaises(ValueError): decode_tim2(bad)
        for offset, value in [(32, 1), (33, 2), (34, 2), (35, 4)]:
            bad = bytearray(self.source); bad[offset] = value
            with self.assertRaises(ValueError): decode_tim2(bytes(bad))

    def test_equal_size_palette_and_unselected_bytes_preserved(self):
        output = self.apply()
        self.assertNotEqual(output, self.source)
        self.assertEqual(len(output), len(self.source))
        allowed = {64 + y * 32 + x for y in range(4, 20) for x in range(4, 28)}
        self.assertTrue(all(n in allowed for n, (a, b) in enumerate(zip(self.source, output)) if a != b))
        self.assertEqual(output[64 + 768:], self.source[64 + 768:])
        self.assertEqual(self.apply(), output)

    def test_source_hash_profile_and_rectangle_lock(self):
        for key, value in [("sha256", "0" * 64), ("profile", [31, 24, 5, 3])]:
            r = deepcopy(self.recipe); r[key] = value
            with self.assertRaises(ValueError): self.apply(r)
        for field, value in [("source_pixels_sha256", "0" * 64), ("rect", [-1, 4, 24, 16]), ("rect", [4, 4, 100, 16]), ("rect", [True, 4, 24, 16]), ("rect", [1, 2, 3])]:
            r = deepcopy(self.recipe); r["slots"][0][field] = value
            with self.assertRaises(ValueError): self.apply(r)

    def test_rejects_missing_glyph_empty_nul_and_overflow(self):
        for target in ["中", "", "A\0", "A" * 100]:
            with self.assertRaises(ValueError): self.apply(target=target)

    def test_duplicate_overlap_unknown_and_pending(self):
        r = deepcopy(self.recipe); r["slots"] *= 2
        with self.assertRaises(ValueError): self.apply(r)
        r = deepcopy(self.recipe); r["slots"].append({**r["slots"][0], "id": "other"})
        with self.assertRaises(ValueError): patch_texture(self.source, r, {"label": "A", "other": "B"}, self.font)
        r = deepcopy(self.recipe); r["slots"][0]["install"] = False
        with self.assertRaises(ValueError): self.apply(r)

    def test_nonuniform_requires_explicit_reviewed_panel(self):
        r = deepcopy(self.recipe)
        r["slots"][0].update(rect=[12, 8, 6, 6], source_pixels_sha256=digest(bytes([1]) * 36), font_size=3, minimum_font_size=3)
        with self.assertRaises(ValueError): self.apply(r)
        r["slots"][0]["background_mode"] = "reviewed-solid-panel"
        with self.assertRaises(ValueError): self.apply(r)
        r["slots"][0]["review_note"] = "Synthetic text-only rectangle."
        self.assertNotEqual(self.apply(r), self.source)

    def test_preserved_artwork_and_polygon(self):
        r = deepcopy(self.recipe)
        r["slots"][0].update(background_mode="reviewed-solid-panel", review_note="Synthetic polygon.", erase_polygon=[[5, 5], [26, 5], [26, 18], [5, 18]])
        output = self.apply(r)
        self.assertEqual(output[64 + 4 * 32:64 + 5 * 32], self.source[64 + 4 * 32:64 + 5 * 32])
        r["slots"][0]["preserve_rects"] = [[4, 4, 24, 16]]
        with self.assertRaises(ValueError): self.apply(r)

    def fixtures(self):
        resource = res_fixture(self.source)
        entry = parse_res(resource).get("A.TM2")
        texture = deepcopy(self.recipe)
        texture["references"] = [{"resource": "UI.RES", "resource_sha256": digest(resource), "member": "A.TM2", "offset": entry.offset, "size": entry.size}]
        manifest = {"format": "graphics-text-slots", "version": 1, "textures": [texture]}
        locale = {"format": "graphics-translations", "version": 1, "locale": "fixture", "font_sha256": digest(self.font), "entries": [{"id": "label", "target": "A", "status": "draft"}]}
        class Image:
            def read(self, name): return resource
        return resource, Image(), manifest, locale

    def test_build_merges_prior_script_edits_and_uses_verified_font_bytes(self):
        original, image, manifest, locale = self.fixtures()
        earlier = parse_res(original).replace({"TEXT.SCR": b"after!"})
        with patch.object(Path, "read_bytes", side_effect=[self.font, b"changed after validation"]) as read:
            output, report = build_graphics(image, manifest, locale, Path("font.otf"), {"UI.RES": earlier})
        self.assertEqual(read.call_count, 1)
        self.assertEqual(parse_res(output["UI.RES"]).read("TEXT.SCR"), b"after!")
        self.assertEqual(report["installed_slots"], ["label"])
        self.assertEqual(report["changed_texture_members"], 1)

    def test_build_schema_font_and_coverage_guards(self):
        _, image, manifest, locale = self.fixtures()
        for key, value in [("format", "other"), ("version", 2), ("locale", ""), ("font_sha256", "0" * 64), ("entries", [])]:
            bad = deepcopy(locale); bad[key] = value
            with patch.object(Path, "read_bytes", return_value=self.font), self.assertRaises(ValueError): build_graphics(image, manifest, bad, Path("font.otf"))

    def test_build_rejects_source_mutation_and_target_conflict(self):
        original, image, manifest, locale = self.fixtures()
        for field, value in [("resource_sha256", "0" * 64), ("offset", 1), ("size", 1)]:
            bad = deepcopy(manifest); bad["textures"][0]["references"][0][field] = value
            with patch.object(Path, "read_bytes", return_value=self.font), self.assertRaises(ValueError): build_graphics(image, bad, locale, Path("font.otf"))
        previous = parse_res(original).replace({"A.TM2": self.apply()})
        with patch.object(Path, "read_bytes", return_value=self.font), self.assertRaises(ValueError): build_graphics(image, manifest, locale, Path("font.otf"), {"UI.RES": previous})

    def test_pending_rows_reported_and_also_require_glyph_coverage(self):
        original, image, manifest, locale = self.fixtures()
        manifest["textures"][0]["slots"][0]["install"] = False
        with patch.object(Path, "read_bytes", return_value=self.font):
            output, report = build_graphics(image, manifest, locale, Path("font.otf"))
        self.assertEqual(output, {})
        self.assertEqual(report["pending_art_restoration_slots"], ["label"])
        locale["entries"][0]["target"] = "中"
        with patch.object(Path, "read_bytes", return_value=self.font), self.assertRaises(ValueError): build_graphics(image, manifest, locale, Path("font.otf"))


if __name__ == "__main__":
    unittest.main()
