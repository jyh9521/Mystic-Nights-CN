import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from mysticnights.graphics_review import validate_review


class GraphicsReviewTests(unittest.TestCase):
    def setUp(self):
        self.review = json.loads((ROOT / 'assets/graphics-source-review.json').read_text('utf8'))
        self.graphics = json.loads((ROOT / 'assets/graphics-text-slots.json').read_text('utf8'))

    def test_entire_source_inventory_is_classified_and_localized_families_closed(self):
        summary = validate_review(self.review, self.graphics)
        self.assertEqual(summary['unique_textures'], 1140)
        self.assertEqual(summary['physical_members'], 2634)
        self.assertEqual(summary['dispositions']['localized-readable-text'], len(self.graphics['textures']))

    def test_unknown_and_missing_dispositions_rejected(self):
        self.review['textures'][0]['disposition'] = 'not-reviewed'
        with self.assertRaises(ValueError):validate_review(self.review, self.graphics)

    def test_missing_localized_texture_or_duplicate_member_rejected(self):
        data = copy.deepcopy(self.review)
        row = next(r for r in data['textures'] if r['disposition'] == 'localized-readable-text')
        row['disposition'] = 'no-readable-localizable-prose'
        with self.assertRaisesRegex(ValueError, 'coverage'):validate_review(data, self.graphics)
        data = copy.deepcopy(self.review)
        data['textures'][0]['references'].append(data['textures'][0]['references'][0])
        with self.assertRaisesRegex(ValueError, 'Duplicate'):validate_review(data, self.graphics)

    def test_clear_same_filename_variant_cannot_silently_fall_outside_the_catalogue(self):
        data = copy.deepcopy(self.review)
        source = next(r for r in data['textures'] if r['disposition'] == 'localized-readable-text')
        other = next(r for r in data['textures'] if r['disposition'] == 'no-readable-localizable-prose')
        other['references'][0]['member'] = source['references'][0]['member']
        with self.assertRaisesRegex(ValueError, 'variant'):validate_review(data, self.graphics)


if __name__ == '__main__':
    unittest.main()
