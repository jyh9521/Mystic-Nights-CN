"""Capacity repair must be justified by the supported retail parser, not defaults."""
import struct
import unittest
from unittest.mock import patch

from mysticnights import cutscene_subtitles as captions


def source_script(kind=b'VOICE', position=b'0 0 0'):
    lines = [b'SCR_TYPE CUTSCENE', b'INIT_DATA {', b'SOUND_COUNT 4', b'}']
    for index in range(4):
        lines += [b'SOUND {', b'FRAME ' + str(index * 10).encode(),
                  b'NAME SYNTHETIC_' + str(index).encode(),
                  b'SOUND_TYPE ' + kind + b' 1', b'POSITION ' + position, b'}']
    return b'\r\n'.join(lines + [b'END']) + b'\r\n'


def reviewed_cue():
    return {'id': 'synthetic', 'start_frame': 10, 'end_frame_exclusive': 20,
            'text': 'caption', 'status': 'reviewed',
            'source_audio_sha256': 'a' * 64, 'source_transcript': 'synthetic'}


def parser_fixture():
    elf = bytearray(0x160000)
    elf[:7] = b'\x7fELF\x01\x01\x01'
    struct.pack_into('<I', elf, 28, 52)
    struct.pack_into('<HH', elf, 42, 32, 1)
    struct.pack_into('<8I', elf, 52, 1, 128, 0x100000, 0x100000,
                     len(elf) - 128, len(elf) - 128, 7, 128)
    for address, value in captions.SOUND_POSITION_ANCHORS.items():
        data = bytes.fromhex(value)
        offset = captions.address_offset(elf, address, len(data))
        elf[offset:offset + len(data)] = data
    return bytes(elf)


class SoundPositionElisionTests(unittest.TestCase):
    def test_overflow_without_retail_proof_still_fails(self):
        with self.assertRaisesRegex(ValueError, 'exceeds original member capacity'):
            captions.inject_script(source_script(), [reviewed_cue()], str.encode, camera_frames=100)

    def test_verified_ignored_commands_only_are_elided_on_overflow(self):
        source = source_script()
        with patch.object(captions, 'inspect_sound_position_elision', return_value={'anchors': ['synthetic proof']}):
            result, report = captions.inject_script(source, [reviewed_cue()], str.encode,
                                                    camera_frames=100, original_elf=b'synthetic')
        self.assertEqual(len(result), len(source))
        self.assertIn(b'"caption"', result)
        self.assertNotIn(b'POSITION', result)
        self.assertFalse(report['original_tokens_retained'])
        self.assertTrue(report['original_semantics_retained'])
        self.assertEqual(len(report['removed_ignored_commands']), 4)
        self.assertEqual(report['ignored_command_bytes_saved'], 64)
        original = captions._line_blocks(source)
        actual = [(name, body) for name, body in captions._line_blocks(result)[1:] if name != b'CAPTION']
        expected = [(name, [line for line in body if line[0] != b'POSITION']) for name, body in original[1:]]
        self.assertEqual(actual, expected)

    def test_no_elision_or_parser_dependency_when_caption_already_fits(self):
        source = source_script() + b' ' * 200
        with patch.object(captions, 'inspect_sound_position_elision', side_effect=AssertionError('unexpected guard')):
            result, report = captions.inject_script(source, [reviewed_cue()], str.encode,
                                                    camera_frames=100, original_elf=b'not needed')
        self.assertEqual(result.count(b'POSITION 0 0 0'), 4)
        self.assertTrue(report['original_tokens_retained'])
        self.assertEqual(report['removed_ignored_commands'], [])

    def test_nonzero_effect_and_ambiguous_commands_are_not_removed(self):
        sources = [source_script(position=b'1 0 0'), source_script(kind=b'EFFECT'),
                   source_script().replace(b'POSITION 0 0 0', b'POSITION 0 0 0\r\nPOSITION 0 0 0'),
                   source_script().replace(b'SOUND_TYPE VOICE 1', b'SOUND_TYPE VOICE 1\r\nSOUND_TYPE BGM 0')]
        with patch.object(captions, 'inspect_sound_position_elision', return_value={'anchors': []}):
            for source in sources:
                with self.subTest(source=source), self.assertRaisesRegex(ValueError, 'exceeds original member capacity'):
                    captions.inject_script(source, [reviewed_cue()], str.encode,
                                           camera_frames=100, original_elf=b'synthetic')

    def test_parser_guard_binds_hash_size_and_each_anchor(self):
        fixture = parser_fixture()
        with self.assertRaisesRegex(ValueError, 'supported original ELF'):
            captions.inspect_sound_position_elision(fixture)
        with patch.object(captions, 'ELF_SIZE', len(fixture)), patch.object(captions, 'ORIGINAL_ELF_SHA256', captions.sha(fixture)):
            proof = captions.inspect_sound_position_elision(fixture)
            self.assertEqual(len(proof['anchors']), 7)
        for address in captions.SOUND_POSITION_ANCHORS:
            tampered = bytearray(fixture)
            tampered[captions.address_offset(tampered, address, 1)] ^= 1
            with self.subTest(address=address), patch.object(captions, 'ELF_SIZE', len(tampered)), patch.object(captions, 'ORIGINAL_ELF_SHA256', captions.sha(tampered)):
                with self.assertRaisesRegex(ValueError, 'SOUND POSITION anchor mismatch'):
                    captions.inspect_sound_position_elision(bytes(tampered))


if __name__ == '__main__':
    unittest.main()
