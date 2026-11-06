"""Source-bound locale listening decisions; machine evidence stays historical."""
from fractions import Fraction
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SubtitleListeningDataTests(unittest.TestCase):
    def setUp(self):
        self.catalogue = json.loads((ROOT / 'locales/zh-CN/subtitles.json').read_text('utf8'))
        self.cues = {c['id']: c for r in self.catalogue['resources'] for c in r['cues']}

    def test_user_corrections_and_source_context_decision(self):
        expected = {'C005-001_002': '这里是……呃啊……', 'C021-016_001': '呃啊',
                    'C027-021_003': '啊！', 'C012-007_001': '简！'}
        for identifier, text in expected.items():
            self.assertEqual(self.cues[identifier]['text'], text)
        ambiguous = self.cues['C012-007_001']
        self.assertEqual(ambiguous['source_transcript'], '신!')
        self.assertFalse(ambiguous['listening_review']['text_confirmed'])
        self.assertEqual(ambiguous['reference_interpretation']['evidence_level'], 'high-confidence contextual deduction')

    def test_approval_and_actual_timing_are_separate(self):
        self.assertEqual(len(self.cues), 10)
        for cue in self.cues.values():
            self.assertTrue(cue['human_listening_verified'])
            self.assertEqual(cue['status'], 'reviewed')
            self.assertFalse(cue['timing_review']['runtime_sync_verified'])
            self.assertFalse(cue['timing_review']['user_end_frame_approval_supplied'])
            for machine in cue['asr']:
                self.assertFalse(machine['human_listening_verified'])
        self.assertEqual(sum(c['listening_review']['text_confirmed'] for c in self.cues.values()), 9)

    def test_nominal_timing_formula_and_native_boundaries(self):
        for cue in self.cues.values():
            samples = cue['timing_samples']
            duration = Fraction(samples['numerator'] * 60000, samples['denominator'] * 1001)
            ticks = (duration.numerator + duration.denominator - 1) // duration.denominator
            timing = cue['timing_review']
            self.assertEqual(timing['nominal_duration_ticks'], ticks)
            bounds = [cue['start_frame'] + ticks, timing['camera_end_exclusive']]
            bounds += [timing[k] for k in ['next_voice_frame', 'next_out_fade_frame'] if timing[k] is not None]
            self.assertEqual(cue['end_frame_exclusive'], min(bounds))
        self.assertEqual(self.cues['C021-016_001']['end_frame_exclusive'], 410)
        self.assertEqual(self.cues['C021-016_002']['end_frame_exclusive'], 536)
        self.assertEqual(self.cues['C027-021_001']['end_frame_exclusive'], 270)
        self.assertEqual(self.cues['C027-021_003']['end_frame_exclusive'], 1472)

    def test_empty_scenes_are_not_approved_as_silent(self):
        self.assertEqual(len(self.catalogue['resources']), 47)
        self.assertEqual(sum(not r['cues'] for r in self.catalogue['resources']), 42)
        self.assertFalse(self.catalogue['all_speech_transcribed'])
        self.assertFalse(self.catalogue['installation']['enabled_by_default'])


if __name__ == '__main__':
    unittest.main()
