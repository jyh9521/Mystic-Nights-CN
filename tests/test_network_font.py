"""PF parsing/overlay tests use synthetic resources, never shipped game files."""
import hashlib
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mysticnights.network_font import (
    NetworkFontError, allocate_mapping, build_network_font,
    collect_protected_codepoints, decode_glyph, decode_text, encode_text,
    parse_pf, patch_glyph_masks,
)


def make_block(first=0xAC00, glyph_count=4, *, flags=0, spans=None, indices=None):
    width = height = 26
    stride = 352
    spans = spans or [(first, first + glyph_count - 1, 0, 0)]
    indices = list(range(glyph_count)) if indices is None else indices
    n_metrics = glyph_count if flags & 8 else 1
    range_at = 96 + stride * glyph_count
    map_at = range_at + 16 * len(spans)
    metrics_at = (map_at + 2 * len(indices) + 15) & ~15
    palette_at = metrics_at + n_metrics * 16
    size = palette_at + 64
    data = bytearray(size)
    header = [0, 0, size, 0, flags, 0x3F800000, 0x3F800000,
              width | height << 16, 24 | 0xFFFE << 16, 25,
              glyph_count, 96, len(spans), range_at, len(indices), map_at,
              n_metrics, metrics_at, 0, palette_at, 16, palette_at, 0, 0]
    struct.pack_into("<24I", data, 0, *header)
    for i, row in enumerate(spans):
        struct.pack_into("<4I", data, range_at + i * 16, *row)
    struct.pack_into(f"<{len(indices)}H", data, map_at, *indices)
    for i in range(n_metrics):
        struct.pack_into("<8h", data, metrics_at + i * 16, 1, 24, -1, 26, 24, -2, 25 - i, 0)
    for i in range(16):
        data[palette_at + i * 4:palette_at + i * 4 + 4] = bytes((i * 17,) * 3 + (128 if i else 0,))
    return bytes(data)


def make_pf(*blocks):
    blocks = blocks or (make_block(),)
    first = (92 + 4 * len(blocks) + 15) & ~15
    size = first + sum(map(len, blocks))
    data = bytearray(size)
    struct.pack_into("<4I", data, 0, 0, 0, size, 0)
    data[16:25] = b"synthetic"
    struct.pack_into("<4hI", data, 80, 25, -2, 25, 0, len(blocks))
    offset = first
    for i, block in enumerate(blocks):
        struct.pack_into("<I", data, 92 + i * 4, offset)
        data[offset:offset + len(block)] = block
        offset += len(block)
    return bytes(data)


def mutate_u32(data, offset, value):
    result = bytearray(data)
    struct.pack_into("<I", result, offset, value)
    return bytes(result)


def make_outline(path):
    """Make a tiny original rectangle-glyph TTF; no external font assets."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder([".notdef", "test"])
    builder.setupCharacterMap({ord("中"): "test", ord("文"): "test"})
    glyphs = {}
    for name in (".notdef", "test"):
        pen = TTGlyphPen(None)
        pen.moveTo((200, 0))
        pen.lineTo((800, 0))
        pen.lineTo((800, 700))
        pen.lineTo((200, 700))
        pen.closePath()
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (1000, 200) for name in glyphs})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    builder.setupNameTable({"familyName": "Synthetic", "styleName": "Regular"})
    builder.setupPost()
    builder.setupMaxp()
    builder.save(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ParserTests(unittest.TestCase):
    def test_complete_profile_and_fixed_metrics(self):
        data = make_pf()
        font = parse_pf(data)
        self.assertEqual(len(font.glyphs), 4)
        self.assertEqual(font.glyphs[0xAC02].index, 2)
        self.assertEqual(font.glyphs[0xAC02].stride, 352)
        self.assertEqual(font.glyphs[0xAC02].advance, 25)
        self.assertEqual(font.data, data)

    def test_range_base_relative_indices_and_missing_sentinel(self):
        spans = [(0xAC00, 0xAC02, 0, 0), (0xAC10, 0xAC11, 3, 2)]
        data = make_pf(make_block(spans=spans, indices=[0, 0xFFFF, 1, 0, 1]))
        font = parse_pf(data)
        self.assertNotIn(0xAC01, font.glyphs)
        self.assertEqual(font.glyphs[0xAC11].index, 3)

    def test_proportional_metrics(self):
        font = parse_pf(make_pf(make_block(flags=8)))
        self.assertEqual(font.glyphs[0xAC02].advance, 23)

    def test_duplicate_keys_follow_first_subfont(self):
        font = parse_pf(make_pf(make_block(), make_block()))
        self.assertEqual(font.glyphs[0xAC00].subfont, 0)
        self.assertEqual(font.shadowed_codepoints, tuple(range(0xAC00, 0xAC04)))

    def test_invalid_outer_header_and_offsets(self):
        data = make_pf()
        cases = [data[:-1], data + b"\0" * 16, mutate_u32(data, 0, 1),
                 mutate_u32(data, 88, 0xFFFFFFFF), mutate_u32(data, 92, 0),
                 mutate_u32(data, 92, len(data) + 16)]
        for case in cases:
            with self.subTest(size=len(case)), self.assertRaises(NetworkFontError):
                parse_pf(case)

    def test_unsupported_subfont_fields_rejected(self):
        data = make_pf()
        first = struct.unpack_from("<I", data, 92)[0]
        for offset, value in [(0, 1), (8, 96), (16, 1), (20, 0), (40, 0),
                              (44, 0), (52, 0xFFFFFFFF), (64, 2), (72, 1),
                              (80, 256), (84, 0), (88, 1)]:
            with self.subTest(offset=offset), self.assertRaises(NetworkFontError):
                parse_pf(mutate_u32(data, first + offset, value))

    def test_bad_range_and_index_rejected(self):
        bad = [make_block(spans=[(0xAC01, 0xAC00, 0, 0)]),
               make_block(spans=[(0xAC00, 0xAC03, 1, 0)]),
               make_block(indices=[0, 1, 2, 4]),
               make_block(spans=[(0xAC00, 0xAC03, 0, 4)]),
               make_block(spans=[(0xAC00, 0xAC01, 0, 0), (0xAC01, 0xAC02, 2, 2)])]
        for block in bad:
            with self.assertRaises(NetworkFontError):
                parse_pf(make_pf(block))

    def test_map_padding_not_silently_ignored(self):
        data = bytearray(make_pf())
        first = struct.unpack_from("<I", data, 92)[0]
        map_at = struct.unpack_from("<I", data, first + 60)[0]
        data[first + map_at + 8] = 1
        with self.assertRaises(NetworkFontError):
            parse_pf(bytes(data))


class MappingTests(unittest.TestCase):
    def test_allocation_preserves_existing_and_protected(self):
        font = parse_pf(make_pf())
        mapping = allocate_mapping(font, ["中가文"], protected_codepoints={0xAC01})
        self.assertEqual(mapping, {"中": 0xAC02, "文": 0xAC03, "가": 0xAC00})
        text = "中가文\n%s 100%"
        self.assertEqual(decode_text(encode_text(text, mapping), mapping), text)
        self.assertEqual(len(encode_text("中文", mapping)), 6)

    def test_exhaustion_scalar_and_nul_failures(self):
        font = parse_pf(make_pf())
        for text, protected in [("中文", range(0xAC00, 0xAC03)), ("\U00020000", ()), ("a\0", ()), ("\ud800", ())]:
            with self.assertRaises(NetworkFontError):
                allocate_mapping(font, [text], protected_codepoints=protected)
        with self.assertRaises(NetworkFontError):
            allocate_mapping(font, ["中"], protected_codepoints={True})

    def test_mapping_validation_and_strict_decode(self):
        for mapping in [{"中": 1}, {"中": 0xD800}, {"中": 0xAC00, "文": 0xAC00}, {"xx": 0xAC00}]:
            with self.assertRaises(NetworkFontError):
                encode_text("中", mapping)
        for data in [b"\xff", b"\0", "文".encode()]:
            with self.assertRaises(NetworkFontError):
                decode_text(data, {"中": 0xAC00})
        with self.assertRaises(NetworkFontError):
            encode_text("文", {"中": 0xAC00})

    def test_aliasing_physical_glyphs_are_not_allocated_twice(self):
        font = parse_pf(make_pf(make_block(indices=[0, 0, 1, 2])))
        mapping = allocate_mapping(font, ["中文"], protected_codepoints={0xAC00})
        self.assertEqual(mapping, {"中": 0xAC02, "文": 0xAC03})
        mapping = allocate_mapping(font, ["中文"], protected_codepoints=())
        self.assertEqual(mapping, {"中": 0xAC00, "文": 0xAC02})
        mapping = allocate_mapping(font, ["가中文"], protected_codepoints=())
        self.assertEqual(mapping, {"中": 0xAC02, "文": 0xAC03, "가": 0xAC00})


class OverlayTests(unittest.TestCase):
    def test_only_pixel_nibbles_change_and_low_nibble_first(self):
        data = make_pf()
        mask = Image.new("L", (26, 26))
        mask.putpixel((0, 0), 255)
        changed = patch_glyph_masks(data, {"中": 0xAC00}, {"中": mask}, protected_codepoints=())
        before, after = parse_pf(data), parse_pf(changed)
        glyph = before.glyphs[0xAC00]
        self.assertEqual(changed[glyph.offset], 15)
        self.assertEqual(data[:glyph.offset], changed[:glyph.offset])
        self.assertEqual(data[glyph.offset + 338:], changed[glyph.offset + 338:])
        self.assertEqual(before.subfonts, after.subfonts)
        self.assertEqual(before.glyphs, after.glyphs)
        self.assertEqual(decode_glyph(after, 0xAC00).getpixel((0, 0)), (255, 255, 255, 255))
        self.assertEqual(len(data), len(changed))

    def test_overlay_rejects_wrong_masks_protection_and_blank(self):
        data = make_pf()
        good = Image.new("L", (26, 26), 255)
        for masks, protected in [({}, ()), ({"中": Image.new("L", (25, 26))}, ()),
                                  ({"中": Image.new("RGB", (26, 26))}, ()),
                                  ({"中": Image.new("L", (26, 26))}, ()),
                                  ({"中": good}, {0xAC00})]:
            with self.assertRaises(NetworkFontError):
                patch_glyph_masks(data, {"中": 0xAC00}, masks, protected_codepoints=protected)

    def test_build_hashes_are_checked_before_outline_loading(self):
        data = make_pf()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "outline.otf"
            path.write_bytes(b"synthetic not a font")
            with self.assertRaisesRegex(NetworkFontError, "PF source SHA"):
                build_network_font(data, ["中"], path, "0" * 64, protected_codepoints=())
            with self.assertRaisesRegex(NetworkFontError, "Outline font SHA"):
                build_network_font(data, ["中"], path, "0" * 64, protected_codepoints=(), expected_source_sha256=hashlib.sha256(data).hexdigest())

    def test_protected_physical_aliases_and_native_mappings(self):
        data = make_pf(make_block(indices=[0, 0, 1, 2]))
        mask = Image.new("L", (26, 26), 255)
        for mapping, protected in [({"中": 0xAC01}, {0xAC00}),
                                   ({"가": 0xAC00, "中": 0xAC01}, ()),
                                   ({"中": 0xAC00}, {True}),
                                   ({"가": 0xAC02}, ())]:
            masks = {c: mask for c, code in mapping.items() if ord(c) != code}
            with self.subTest(mapping=mapping), self.assertRaises(NetworkFontError):
                patch_glyph_masks(data, mapping, masks, protected_codepoints=protected)

    def test_full_build_is_deterministic_and_glyph_only(self):
        data = make_pf()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.ttf"
            font_sha = make_outline(path)
            kwargs = {"protected_codepoints": {0xAC00}, "expected_source_sha256": hashlib.sha256(data).hexdigest()}
            first = build_network_font(data, ["中文", "中文\nA1"], path, font_sha, **kwargs)
            second = build_network_font(data, ["中文\nA1", "中文"], path, font_sha, **kwargs)
            self.assertEqual(first, second)
            self.assertEqual(first.mapping, {"中": 0xAC01, "文": 0xAC02})
            self.assertEqual(len(first.changed_glyphs), 2)
            self.assertEqual(len(first.data), len(data))
            self.assertEqual(parse_pf(first.data).subfonts, parse_pf(data).subfonts)
            self.assertEqual(path.read_bytes()[:4], b"\0\x01\0\0")
            with self.assertRaisesRegex(NetworkFontError, "missing glyphs"):
                build_network_font(data, ["未"], path, font_sha, **kwargs)
            with self.assertRaisesRegex(NetworkFontError, "pixel size"):
                build_network_font(data, ["中"], path, font_sha, pixel_size=25, **kwargs)


class SurveyTests(unittest.TestCase):
    @staticmethod
    def elf(payload):
        data = bytearray(84 + len(payload))
        data[:7] = b"\x7fELF\x01\x01\x01"
        struct.pack_into("<H", data, 18, 8)
        struct.pack_into("<I", data, 28, 52)
        struct.pack_into("<HH", data, 42, 32, 1)
        struct.pack_into("<8I", data, 52, 1, 84, 0x100000, 0x100000, len(payload), len(payload), 4, 16)
        data[84:] = payload
        return bytes(data)

    def test_only_complete_printable_utf8_load_strings(self):
        data = self.elf("가나\nA".encode() + b"\0" + b"\x01" + "다".encode() + b"\0" + "라".encode())
        self.assertEqual(collect_protected_codepoints(data), {ord("가"), ord("나")})

    def test_invalid_elf_boundaries(self):
        data = self.elf("가\0".encode())
        for bad in [b"not elf", data[:-1], mutate_u32(data, 28, 0xFFFFFFF0), mutate_u32(data, 52 + 20, 0)]:
            with self.assertRaises(NetworkFontError):
                collect_protected_codepoints(bad)


class InspectorTests(unittest.TestCase):
    @staticmethod
    def load_inspector():
        root = Path(__file__).resolve().parents[1]
        with patch.object(sys, "path", [str(root / "tools"), *sys.path]):
            spec = importlib.util.spec_from_file_location("network_font_inspector", root / "tools/inspect_network_font.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        return module

    def test_new_output_and_late_failure_are_transactional(self):
        inspector = self.load_inspector()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "assets").mkdir()
            outline = root / "synthetic.ttf"
            font_sha = make_outline(outline)
            (root / "assets/font-source.json").write_text(json.dumps({"filename": "synthetic.ttf", "sha256": font_sha}), encoding="utf8")
            source = "원래 문자열"
            elf = source.encode("utf8") + b"\0"
            original = make_pf()
            class Image:
                def read(self, name):
                    return {"NETGUICD.ELF": elf, "NETGUI/KOREAN.PF": original}[name]
            catalogue = root / "catalogue.json"
            catalogue.write_text(json.dumps({"entries": [{"id": "NETGUICD.ELF@00000000", "offset": 0,
                "source": source, "source_bytes": len(elf) - 1, "source_sha256": hashlib.sha256(elf[:-1]).hexdigest(),
                "resource": "NETGUICD.ELF", "target": "中文", "status": "draft"}]}), encoding="utf8")
            output = root / "result"
            argv = ["inspect_network_font.py", "--iso", str(root / "unused.iso"), "--output", str(output),
                    "--catalogue", str(catalogue), "--font", str(outline)]
            def synthetic_build(*args, **kwargs):
                return build_network_font(*args, **kwargs, expected_source_sha256=hashlib.sha256(original).hexdigest())
            with patch.object(inspector, "ROOT", root), patch.object(inspector, "load_version", return_value={}), \
                    patch.object(inspector, "verify_original", return_value=Image()), \
                    patch.object(inspector, "inspect", return_value=({"fixture": True}, set())), \
                    patch.object(inspector, "build_network_font", side_effect=synthetic_build), \
                    patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
                with patch.object(inspector, "render_preview", side_effect=ValueError("late preview failure")):
                    with self.assertRaisesRegex(ValueError, "late preview"):
                        inspector.main()
                self.assertFalse(output.exists())
                self.assertEqual(list(root.glob(".result-*")), [])
                inspector.main()
                saved = (output / "MODIFIED_FILE.PF").read_bytes()
                report = json.loads((output / "report.json").read_text(encoding="utf8"))
                self.assertEqual(report["build"]["modified_pf_sha256"], hashlib.sha256(saved).hexdigest())
                self.assertEqual(report["build"]["translated_fields"], 1)
                self.assertNotEqual(saved, original)
                self.assertTrue((output / "glyph-preview.png").is_file())
                with self.assertRaises(FileExistsError):
                    inspector.main()
                self.assertEqual((output / "MODIFIED_FILE.PF").read_bytes(), saved)
                self.assertEqual(Image().read("NETGUI/KOREAN.PF"), original)


if __name__ == "__main__":
    unittest.main()
