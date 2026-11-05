import json
from pathlib import Path
import tempfile
import unittest
from PIL import Image
from mysticnights.image_review import (canonical, script_json, write_png, read_feedback,
                                      stable_order, attach_previous_feedback)


class ImageReviewTests(unittest.TestCase):
    def test_json_does_not_end_script(self):
        value = {'label': '</script><img onerror="bad()">', 'separator': '\u2028\u2029'}
        encoded = script_json(value)
        self.assertNotIn('<', encoded)
        self.assertNotIn('\u2028', encoded)
        self.assertEqual(json.loads(encoded), value)

    def test_canonical_order_and_utf8(self):
        self.assertEqual(canonical({'b': 1, 'a': '中文'}), canonical({'a': '中文', 'b': 1}))
        self.assertTrue(canonical({}).endswith(b'\n'))

    def test_png_preserves_hidden_rgb_and_alpha(self):
        with tempfile.TemporaryDirectory() as tmp:
            im = Image.new('RGBA', (3, 1))
            im.putdata([(12, 13, 14, 0), (40, 50, 60, 128), (100, 110, 120, 255)])
            path = Path(tmp) / 'preview.png'
            row = write_png(im, path)
            self.assertEqual(row['path'], 'preview.png')
            self.assertEqual(len(row['sha256']), 64)
            with Image.open(path) as reopened:
                self.assertEqual(list(reopened.get_flattened_data()), list(im.get_flattened_data()))

    def fixture(self):
        item = {'id': 'tim2:a', 'number': 1, 'source_sha256': 'a' * 64,
                'localized_sha256': 'b' * 64, 'references': [{'resource': 'RES/X.RES', 'member': 'X.TM2'}]}
        review = {'revision': 'v1', 'source_iso_sha256': 'c' * 64, 'items': [item]}
        row = {**item, 'comment': '逗号,引号"\n下一行', 'status': 'issue'}
        value = {'format': 'disc-image-feedback', 'version': 1, 'source_iso_sha256': 'c' * 64, 'entries': [row]}
        return review, value

    def test_json_roundtrip_and_stale_hash(self):
        review, value = self.fixture()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'feedback.json'
            path.write_bytes(b'\xef\xbb\xbf' + canonical(value))
            result = read_feedback(path, review)
            self.assertEqual(result['opinion_entries'], 1)
            self.assertFalse(result['entries'][0]['stale'])
            value['entries'][0]['localized_sha256'] = 'e' * 64
            path.write_bytes(canonical(value))
            self.assertTrue(read_feedback(path, review)['entries'][0]['stale'])

    def test_blank_is_not_approval(self):
        review, value = self.fixture()
        value['entries'][0].update(comment='', status='unreviewed')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'feedback.json'
            path.write_bytes(canonical(value))
            self.assertEqual(read_feedback(path, review)['entries'], [])

    def test_unknown_duplicate_and_source_rejected(self):
        from copy import deepcopy
        review, value = self.fixture()
        variants = [deepcopy(value) for _ in range(3)]
        variants[0]['entries'][0]['id'] = 'wrong'
        variants[1]['entries'].append(variants[1]['entries'][0])
        variants[2]['entries'][0]['source_sha256'] = 'f' * 64
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'feedback.json'
            for bad in variants:
                path.write_bytes(canonical(bad))
                with self.assertRaises(ValueError):
                    read_feedback(path, review)

    def test_csv_preserves_multiline_and_quotes(self):
        import csv
        review, value = self.fixture()
        row = value['entries'][0]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'feedback.csv'
            with path.open('w', encoding='utf-8-sig', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerow(['image_id', 'source_sha256', 'localized_sha256', 'status', 'feedback'])
                writer.writerow([row['id'], row['source_sha256'], row['localized_sha256'], row['status'], row['comment']])
            self.assertEqual(read_feedback(path, review)['entries'][0]['comment'], row['comment'])

    def test_retaining_image_does_not_renumber_source_order(self):
        recipe = {'format': 'disc-image-review-order', 'version': 1,
                  'source_iso_sha256': 's', 'tim2': ['b', 'a']}
        self.assertEqual(stable_order({'a': {}, 'b': {}}, recipe, 's'), ['b', 'a'])
        for keys in (['b', 'b'], ['b'], ['a', 'b', 'c']):
            with self.assertRaises(ValueError):
                stable_order({'a': {}, 'b': {}}, {**recipe, 'tim2': keys}, 's')
        with self.assertRaises(ValueError):
            stable_order({'a': {}, 'b': {}}, recipe, 'other-disc')

    def test_changed_feedback_is_history_not_new_approval(self):
        review, value = self.fixture()
        value['entries'][0].update(status='ok', localized_sha256='e' * 64)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'feedback.json'; path.write_bytes(canonical(value))
            attach_previous_feedback(review, path)
        item = review['items'][0]
        self.assertTrue(item['previous_feedback']['changed'])
        self.assertEqual(item['previous_feedback']['comment'], value['entries'][0]['comment'])
        self.assertNotIn('initial_status', item)
        self.assertEqual(review['previous_feedback_summary'],
                         {'carried_confirmations': 0, 'changed_for_recheck': 1})

    def test_unchanged_confirmation_carries_but_issue_not_auto_approved(self):
        for status, expected in [('ok', 1), ('issue', 0)]:
            review, value = self.fixture(); value['entries'][0]['status'] = status
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'feedback.json'; path.write_bytes(canonical(value))
                attach_previous_feedback(review, path)
            self.assertEqual(review['previous_feedback_summary']['carried_confirmations'], expected)
            self.assertEqual(review['items'][0].get('initial_status'), 'ok' if expected else None)


if __name__ == '__main__':
    unittest.main()
