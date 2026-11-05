"""Label/icon spacing is independent of glyph size and English word widths."""
from copy import deepcopy
import unittest
from PIL import Image, ImageDraw
from mysticnights.artwork_checks import check_anchor_gaps


class AnchorGapTests(unittest.TestCase):
    def setUp(self):
        self.im = Image.new('RGBA', (100, 32))
        d = ImageDraw.Draw(self.im)
        d.rectangle((5, 5, 24, 17), fill='white')
        d.rectangle((55, 5, 74, 17), fill='white')
        self.check = {'id': 'equal-gap', 'axis': 'x', 'max_gap_difference': 0,
                      'min_gap': 3, 'min_row_pixels': 1, 'min_column_pixels': 1,
                      'members': [self.member([0, 0, 28, 25], [28, 5, 10, 13]),
                                  self.member([50, 0, 28, 25], [78, 5, 10, 13])]}

    @staticmethod
    def member(rect, anchor, side='before'):
        return {'label': {'rect': rect, 'rgba_min': [200, 200, 200, 200],
                          'rgba_max': [255, 255, 255, 255]},
                'anchor': anchor, 'side': side}

    def test_equal_spacing(self):
        r = check_anchor_gaps(self.im, [self.check])[0]
        self.assertEqual(r['gaps'], [3, 3])

    def test_equal_size_does_not_prove_equal_gap(self):
        c = deepcopy(self.check); c['members'][1]['anchor'][0] += 5
        with self.assertRaisesRegex(ValueError, 'gaps='):
            check_anchor_gaps(self.im, [c])

    def test_reject_crowding_even_if_both_equal(self):
        c = deepcopy(self.check)
        for m in c['members']: m['anchor'][0] -= 3
        with self.assertRaisesRegex(ValueError, 'minimum'):
            check_anchor_gaps(self.im, [c])

    def test_label_after_anchor_and_vertical_axis(self):
        c = deepcopy(self.check)
        for m, x in zip(c['members'], [0, 50]):
            m['anchor'] = [x, 5, 2, 13]; m['side'] = 'after'
        self.assertEqual(check_anchor_gaps(self.im, [c])[0]['gaps'], [3, 3])
        c['axis'] = 'y'
        for m in c['members']: m['anchor'] = [0, 0, 2, 2]
        self.assertEqual(check_anchor_gaps(self.im, [c])[0]['gaps'], [3, 3])

    def test_invalid_recipe_and_empty_ink(self):
        for key, value in [('axis', 'z'), ('min_gap', True), ('max_gap_difference', -1),
                           ('id', ''), ('members', [])]:
            c = deepcopy(self.check); c[key] = value
            with self.assertRaises(ValueError): check_anchor_gaps(self.im, [c])
        for anchor in [[-1, 0, 3, 4], [99, 0, 3, 4], [0, 0, 0, 4], [0, 0, 1]]:
            c = deepcopy(self.check); c['members'][0]['anchor'] = anchor
            with self.assertRaises(ValueError): check_anchor_gaps(self.im, [c])
        c = deepcopy(self.check); c['members'][0]['side'] = 'around'
        with self.assertRaises(ValueError): check_anchor_gaps(self.im, [c])
        with self.assertRaises(ValueError): check_anchor_gaps(Image.new('RGBA', self.im.size), [self.check])
        with self.assertRaises(ValueError): check_anchor_gaps(self.im, [self.check, self.check])

    def test_cross_axis_alignment_is_measured_separately_from_gap(self):
        c = deepcopy(self.check)
        c['max_cross_axis_center_error_twice'] = 1
        r = check_anchor_gaps(self.im, [c])[0]
        self.assertEqual([m['cross_axis_center_error_twice'] for m in r['members']], [0, 0])

    def test_equal_gaps_and_sizes_do_not_hide_vertical_misalignment(self):
        c = deepcopy(self.check)
        c['max_cross_axis_center_error_twice'] = 1
        c['members'][1]['anchor'][1] += 1
        with self.assertRaisesRegex(ValueError, 'cross-axis center'):
            check_anchor_gaps(self.im, [c])

    def test_vertical_spacing_can_check_horizontal_alignment(self):
        c = deepcopy(self.check); c['axis'] = 'y'
        c['max_cross_axis_center_error_twice'] = 1
        for m, x in zip(c['members'], [5, 55]):
            m['anchor'] = [x, 21, 20, 8]
        self.assertEqual(check_anchor_gaps(self.im, [c])[0]['gaps'], [3, 3])
        c['members'][1]['anchor'][0] += 1
        with self.assertRaisesRegex(ValueError, 'cross-axis center'):
            check_anchor_gaps(self.im, [c])

    def test_invalid_cross_axis_alignment_tolerance_is_rejected(self):
        for value in [True, -1, 201, '1', None]:
            c = deepcopy(self.check); c['max_cross_axis_center_error_twice'] = value
            with self.assertRaises(ValueError): check_anchor_gaps(self.im, [c])


if __name__ == '__main__':
    unittest.main()
