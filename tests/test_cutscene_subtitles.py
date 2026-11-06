"""Offline regression tests for the explicit cutscene caption feature.

Synthetic ELF below bypasses only retail identity checks; it does not pretend
to be a game or transcript. Actual retail anchor checks have a separate CLI.
"""
import copy
import struct
import unittest
from unittest.mock import patch

from mysticnights import cutscene_subtitles as captions


def cue(start=10, end=20, text='caption', **changes):
    return {'id': f'cue-{start}', 'start_frame': start, 'end_frame_exclusive': end,
            'text': text, 'status': 'reviewed', 'source_audio_sha256': 'a' * 64,
            'source_transcript': 'synthetic fixture source', **changes}


def script():
    return (b'SCR_TYPE CUTSCENE\r\n\r\nINIT_DATA {\r\n OBJECT_COUNT 1\r\n SOUND_COUNT 2\r\n}\r\n'
            b'OBJECT {\r\n FRAME 0\r\n NAME X\r\n}\r\n'
            b'SOUND {\r\n FRAME 10\r\n NAME VOICE_A\r\n SOUND_TYPE VOICE 1\r\n}\r\n'
            b'SOUND {\r\n FRAME 10\r\n NAME EFFECT_A\r\n SOUND_TYPE EFFECT 1\r\n}\r\n'
            b';' + b' disposable comment' * 80 + b'\r\nEND\r\n')


def synthetic_elf():
    original = bytearray(b'\x55' * 0x90000)
    original[:128] = bytes(128); original[:7] = b'\x7fELF\x01\x01\x01'
    struct.pack_into('<I', original, 28, 52)
    struct.pack_into('<HH', original, 42, 32, 1)
    struct.pack_into('<8I', original, 52, 1, 128, 0x100000, 0x100000, len(original) - 128, len(original) - 128, 7, 128)
    entries = []; current = bytearray(original)
    for i in range(60):
        offset = 0x70000 + i * 128; capacity = 127
        source = ('source ' + str(i) + ' ' + 'x' * (capacity - len('source ' + str(i) + ' ') - 1)).encode() + b'\0'
        original[offset:offset + capacity] = source
        current[offset:offset + capacity] = b't\0'.ljust(capacity, b'\0')
        entries.append({'id': f'owner-{i:03d}', 'kind': 'elf', 'resource': 'SCKA_200.55',
                        'offset': offset, 'capacity': capacity, 'source_sha256': captions.sha(source), 'target': 't'})
    return bytes(original), bytes(current), entries


class CaptionScriptTests(unittest.TestCase):
    def test_stable_same_frame_merge_and_equal_length(self):
        source = script(); result, report = captions.inject_script(source, [cue()], str.encode, camera_frames=100)
        self.assertEqual(len(result), len(source))
        blocks = captions._blocks(captions._tokens(result))
        self.assertEqual([name for name, body in blocks], [b'INIT_DATA', b'OBJECT', b'SOUND', b'SOUND', b'CAPTION'])
        self.assertEqual(blocks[-1][1], [b'FRAME', b'10', b'CONTENTS', b'10', b'"caption"'])
        self.assertEqual(result.splitlines()[0], b'SCR_TYPE CUTSCENE')
        self.assertTrue(report['original_tokens_retained'])

    def test_captions_are_interleaved_not_appended_after_later_events(self):
        source = script().replace(b'FRAME 10\r\n NAME EFFECT_A', b'FRAME 30\r\n NAME EFFECT_A')
        result, _ = captions.inject_script(source, [cue(), cue(25, 29, 'next')], str.encode, camera_frames=100)
        frames = [captions._frame(body) for _, body in captions._blocks(captions._tokens(result))[1:]]
        self.assertEqual(frames, [0, 10, 10, 25, 30])

    def test_no_cues_preserves_original_bytes_and_comments(self):
        source = script(); result, report = captions.inject_script(source, [], str.encode, camera_frames=100)
        self.assertEqual(result, source); self.assertFalse(report['changed'])

    def test_drafts_are_not_silently_promoted(self):
        for status in ['asr-draft', 'draft', '', None]:
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, 'not audio/transcript reviewed'):
                captions.inject_script(script(), [cue(status=status)], str.encode, camera_frames=100)

    def test_overlapping_empty_out_of_range_and_unbound_cues_rejected(self):
        invalid = [[cue(), cue(15, 25)], [cue(text='')], [cue(end=101)],
                   [cue(source_audio_sha256='not-a-hash')], [cue(source_transcript='')],
                   [cue(), cue(id='cue-10', start_frame=30, end_frame_exclusive=40)]]
        for rows in invalid:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                captions.inject_script(script(), rows, str.encode, camera_frames=100)

    def test_capacity_and_quote_encoding_fail_closed(self):
        for source, rows in [(b'SCR_TYPE CUTSCENE INIT_DATA { } END', [cue()]), (script(), [cue(text='x' * 511)])]:
            with self.assertRaises(ValueError):
                captions.inject_script(source, rows, str.encode, camera_frames=100)
        with self.assertRaises(ValueError):
            captions.inject_script(script(), [cue()], lambda _: b'bad"quote', camera_frames=100)

    def test_comments_inside_strings_and_original_tokens_are_preserved(self):
        source = script().replace(b'NAME X', b'NAME "x ; a word"')
        result, _ = captions.inject_script(source, [cue(text='50% complete')], str.encode, camera_frames=100)
        self.assertIn(b'"x ; a word"', result)
        self.assertIn(b'"50% complete"', result)

    def test_nonmonotonic_source_and_existing_track_rejected(self):
        for source in [script().replace(b'FRAME 10\r\n NAME EFFECT_A', b'FRAME 5\r\n NAME EFFECT_A'),
                       script().replace(b'OBJECT_COUNT 1', b'CAPTION_COUNT 1\r\n OBJECT_COUNT 1')]:
            with self.assertRaises(ValueError):
                captions.inject_script(source, [cue()], str.encode, camera_frames=100)

    def test_single_line_compaction_is_rejected_by_native_line_reader(self):
        with self.assertRaisesRegex(ValueError, 'header/END command lines'):
            captions.inject_script(b' '.join(captions._tokens(script())), [cue()], str.encode, camera_frames=100)
        result, report = captions.inject_script(script(), [cue()], str.encode, camera_frames=100)
        self.assertIn(b'CAPTION {\r\nFRAME 10\r\nCONTENTS 10 "caption"\r\n}', result)
        self.assertTrue(report['retail_GetToken_command_lines_retained'])


class CaptionCodeTests(unittest.TestCase):
    def setUp(self):
        self.original, self.current, self.entries = synthetic_elf()
        with patch.object(captions, 'inspect_engine', return_value={'anchors': []}):
            self.modified, self.report = captions.build_engine_patch(self.original, self.current, self.entries, {})

    def replay(self, frame, **changes):
        arguments = {'frame': frame, 'nodes': [{'type': 1, 'index': 0, 'frame': 10}, {'type': 2, 'index': 0, 'frame': 10}],
                     'captions': [{'end_frame_inclusive': 19, 'text': b'literal %s <BR> next'}]}
        arguments.update(changes)
        return captions.replay_engine_hook(self.modified, self.report, **arguments)

    def test_frame_before_start_start_last_and_after_end(self):
        for frame, count in [(0, 0), (10, 0), (11, 2), (20, 2), (21, 0), (32767, 0)]:
            with self.subTest(frame=frame):
                result = self.replay(frame)
                self.assertEqual(len(result['draws']), count)
                self.assertEqual(result['flip_calls'], 1)
                self.assertTrue(result['font_environment_restored'])
                self.assertTrue(result['saved_registers_128bit_restored'])

    def test_literal_text_shadow_and_foreground(self):
        result = self.replay(11)
        self.assertEqual([row['rgba'] for row in result['draws']], [[0, 0, 0, 128], [128, 128, 128, 128]])
        self.assertEqual([(row['x'], row['y'], row['width']) for row in result['draws']], [(42, 352, 550), (40, 350, 550)])
        self.assertEqual([bytes.fromhex(row['text_hex']) for row in result['draws']], [b'literal %s <BR> next'] * 2)

    def test_skip_empty_scene_and_clear_have_no_lingering_caption(self):
        for changes in [{'skip': True}, {'nodes': []}, {'captions': []}, {'frame': -1}]:
            result = self.replay(**{'frame': 11, **changes})
            self.assertEqual(result['draws'], [])

    def test_bad_caption_index_is_not_dereferenced(self):
        for index in [-1, 1, 32767]:
            result = self.replay(11, nodes=[{'type': 2, 'index': index, 'frame': 10}])
            self.assertEqual(result['draws'], [])

    def test_adjacent_cues_and_same_frame_other_nodes(self):
        nodes = [{'type': 0, 'index': 0, 'frame': 0}, {'type': 2, 'index': 0, 'frame': 10},
                 {'type': 1, 'index': 0, 'frame': 20}, {'type': 2, 'index': 1, 'frame': 20}]
        values = [{'end_frame_inclusive': 19, 'text': b'first'}, {'end_frame_inclusive': 24, 'text': b'second'}]
        for frame, expected in [(20, b'first'), (21, b'second'), (25, b'second'), (26, None)]:
            result = self.replay(frame, nodes=nodes, captions=values)
            self.assertEqual([bytes.fromhex(row['text_hex']) for row in result['draws']], [expected] * 2 if expected else [])

    def test_fragmented_bridges_and_exact_rollback(self):
        self.assertGreater(len(self.report['padding_owners']), 3)
        self.assertEqual(captions.reverse_engine_patch(self.modified, self.report), self.current)
        for row in self.report['padding_owners']:
            self.assertGreater(row['offset'], row['first_nul_offset'])
        changed = {i for i, (a, b) in enumerate(zip(self.current, self.modified)) if a != b}
        allowed = {i for row in self.report['writes'] for i in range(row['offset'], row['offset'] + len(bytes.fromhex(row['after'])))}
        self.assertLessEqual(changed, allowed)

    def test_dirty_padding_is_not_used_and_unbound_owner_fails(self):
        current = bytearray(self.current); first = self.entries[0]
        current[first['offset'] + 12] = 1
        with patch.object(captions, 'inspect_engine', return_value={'anchors': []}):
            _, report = captions.build_engine_patch(self.original, bytes(current), self.entries, {})
        self.assertNotIn(first['id'], [row['owner_id'] for row in report['padding_owners']])
        entries = copy.deepcopy(self.entries); entries[0]['source_sha256'] = 'f' * 64
        with patch.object(captions, 'inspect_engine', return_value={'anchors': []}), self.assertRaises(ValueError):
            captions.build_engine_patch(self.original, self.current, entries, {})

    def test_unknown_original_and_tampered_rollback_rejected(self):
        with self.assertRaises(ValueError):
            captions.inspect_engine(self.original)
        modified = bytearray(self.modified); modified[0x300] ^= 1
        with self.assertRaises(ValueError):
            captions.reverse_engine_patch(bytes(modified), self.report)


if __name__ == '__main__':
    unittest.main()
