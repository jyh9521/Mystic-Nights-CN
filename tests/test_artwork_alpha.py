"""Material alpha is authored data, not an inherited old-text mask."""
import unittest
from PIL import Image
from test_graphics import tim2_fixture, digest
from mysticnights.graphics import decode_tim2
from mysticnights.artwork import import_indexed_pixels
from mysticnights.artwork_checks import check_clear_regions, check_state_pairs


class MaterialAlphaTests(unittest.TestCase):
    def setUp(self):
        b = bytearray(tim2_fixture())
        p = 64 + 32 * 24
        b[p+8:p+12] = bytes([80, 30, 10, 105])
        b[p+12:p+16] = bytes([81, 31, 11, 104])
        self.source = bytes(b)
        self.image, self.info = decode_tim2(self.source)
        self.image.putpixel((0, 0), (81, 31, 11, 209))
        self.rule = {'rect': [0, 0, 1, 1], 'min_alpha': 209, 'max_alpha': 209}

    def apply(self, rules):
        return import_indexed_pixels(self.source, self.image, [[0, 0, 1, 1]],
                    source_sha256=digest(self.source), palette_constraints=rules)

    def test_restricts_quantization_without_changing_header_or_clut(self):
        b = self.apply([self.rule])
        self.assertEqual(b[64], 2)
        self.assertEqual(b[:64], self.source[:64])
        self.assertEqual(b[self.info['palette_offset']:], self.source[self.info['palette_offset']:])
        self.assertEqual(b[65:self.info['palette_offset']], self.source[65:self.info['palette_offset']])

    def test_rejects_empty_candidate_palette(self):
        with self.assertRaisesRegex(ValueError, 'No palette colors'):
            self.apply([{**self.rule, 'min_alpha': 210, 'max_alpha': 210}])

    def test_rejects_overlap_protected_and_invalid_ranges(self):
        for rules in [[self.rule, self.rule], [{**self.rule, 'rect': [0, 0, 2, 1]}],
                      [{**self.rule, 'min_alpha': True}], [{**self.rule, 'min_alpha': 210}]]:
            with self.assertRaises(ValueError): self.apply(rules)

    def test_unchanged_rgba_must_still_obey_constraint(self):
        self.image.putpixel((0, 0), (81, 31, 11, 207))
        b = bytearray(self.source); b[64] = 3; self.source = bytes(b)
        self.assertEqual(self.apply([self.rule])[64], 2)

    def test_alpha_band_catches_old_letter_mask(self):
        im = Image.new('RGBA', (3, 1), (80, 30, 10, 209))
        c = {'id': 'clean-bed', 'rect': [0, 0, 3, 1], 'min_alpha': 209, 'max_alpha': 209}
        self.assertEqual(check_clear_regions(im, [c])[0]['nontransparent_pixels'], 0)
        im.putpixel((1, 0), (80, 30, 10, 207))
        with self.assertRaisesRegex(ValueError, 'below minimum pixels=1'):
            check_clear_regions(im, [c])

    def test_alpha_band_rejects_invalid_minimum(self):
        for minimum in [-1, True, 210]:
            with self.assertRaises(ValueError):
                check_clear_regions(self.image, [{'id': 'bad', **self.rule, 'min_alpha': minimum}])

    def test_centering_rejects_equally_sized_but_displaced_words(self):
        im = Image.new('RGBA', (12, 5), (255, 255, 255, 255))
        s = {'rect': [0, 0, 4, 5], 'rgba_min': [200]*4, 'rgba_max': [255]*4,
             'center_twice': [4, 5]}
        c = {'id': 'center', 'normal': s, 'selected': {**s, 'center_twice': [8, 5]},
             'min_row_pixels': 1, 'min_column_pixels': 1,
             'max_width_difference': 0, 'max_height_difference': 0,
             'max_center_error_twice': 1}
        with self.assertRaisesRegex(ValueError, 'center error'):
            check_state_pairs(im, [c])
        c['selected']['center_twice'] = [4, 5]
        self.assertEqual(len(check_state_pairs(im, [c])), 1)
