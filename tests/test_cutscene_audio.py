import struct
import unittest
from pathlib import Path
import hashlib
import importlib.util
import json
import sys
import tempfile

from mysticnights.cutscene_audio import (
    AudioFormatError, make_vag, parse_vag, parse_mih, split_mib,
    cutscene_sound_commands,
)


class CutsceneAudioTests(unittest.TestCase):
    def test_vag_identity_and_big_endian_rate(self):
        payload = bytes(32)
        data = make_vag(payload, 48000, 'C005')
        info = parse_vag(data)
        self.assertEqual((info.sample_rate, info.data_size, info.name), (48000, 32, 'C005'))
        self.assertEqual(info.samples, 56)

    def test_vag_rejects_size_mismatch(self):
        with self.assertRaises(AudioFormatError):
            parse_vag(make_vag(bytes(32), 48000)[:-1])

    def test_vag_rejects_unknown_magic(self):
        with self.assertRaises(AudioFormatError):
            parse_vag(bytes(80))

    def test_vag_opaque_debug_name_is_not_guessed_or_dropped(self):
        data = bytearray(make_vag(bytes(16), 48000))
        data[32:35] = b'\xbd\xba\xb1'
        info = parse_vag(bytes(data))
        self.assertIsNone(info.name)
        self.assertEqual(info.name_bytes_hex, 'bdbab1')

    def test_vag_rejects_non_frame_data(self):
        with self.assertRaises(AudioFormatError):
            make_vag(bytes(17), 48000)

    def test_mih_last_frame_is_high_24_bits(self):
        header = struct.pack('<6I', 64, (16 << 8) | 32, 2, 48000, 32, 2) + bytes(40)
        info = parse_mih(header)
        self.assertEqual((info.channels, info.interleave, info.block_count, info.last_block), (2, 32, 2, 16))
        self.assertEqual(info.samples, 84)
        left, right = split_mib(info, b'A' * 32 + b'B' * 32 + b'C' * 32 + b'D' * 32)
        self.assertEqual(left, b'A' * 32 + b'C' * 16)
        self.assertEqual(right, b'B' * 32 + b'D' * 16)

    def test_mih_truncated_or_malformed_rejected(self):
        for data in [bytes(63), bytes(64), struct.pack('<6I', 64, 32, 0, 48000, 32, 2) + bytes(40)]:
            with self.assertRaises(AudioFormatError):
                parse_mih(data)

    def test_mib_incomplete_interleave_rejected(self):
        header = struct.pack('<6I', 64, 32, 2, 48000, 32, 2) + bytes(40)
        with self.assertRaises(AudioFormatError):
            split_mib(parse_mih(header), bytes(127))

    def test_cutscene_sound_retains_exact_frame_and_type(self):
        data = b'SCR_TYPE CUTSCENE\r\nSOUND {\n FRAME 720\n NAME 001-002\\001_001.VAG\n SOUND_TYPE VOICE 1\n POSITION 0 0 0\n}\n'
        commands = cutscene_sound_commands(data)
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0]['frame'], 720)
        self.assertEqual(commands[0]['sound_type'], 'VOICE')
        self.assertEqual(commands[0]['name'], '001-002\\001_001.VAG')

    def test_comments_do_not_create_sound_commands(self):
        self.assertEqual(cutscene_sound_commands(b'SCR_TYPE CUTSCENE\n; SOUND {\n; FRAME 42\n; NAME fake\n; SOUND_TYPE VOICE 1\n; }\n'), [])

    def test_missing_sound_fields_rejected(self):
        with self.assertRaises(AudioFormatError):
            cutscene_sound_commands(b'SCR_TYPE CUTSCENE\nSOUND { FRAME 2\n NAME foo\n}\n')


class AsrInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location('audio_transcribe_tool', root / 'tools/transcribe_cutscene_audio.py')
        cls.tool = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(root / 'tools'))
        try:
            spec.loader.exec_module(cls.tool)
        finally:
            sys.path.pop(0)
        cls.source = json.loads((root / 'assets/game-version.json').read_text('utf8'))['iso']['sha256']

    def fixture(self, folder):
        wav = folder / 'clip.wav'
        wav.write_bytes(b'unit fixture, never sent to an ASR engine')
        row = {'id': 'voice:unit', 'kind': 'vag', 'resource': 'UNIT.VAG',
               'wav': {'path': 'clip.wav', 'size': wav.stat().st_size,
                       'sha256': hashlib.sha256(wav.read_bytes()).hexdigest()}}
        manifest = {'format': 'cutscene-audio-survey', 'version': 1,
                    'source_iso_sha256': self.source, 'audio': [row]}
        target = folder / 'manifest.json'
        target.write_text(json.dumps(manifest), 'utf8')
        return manifest, row, target

    def test_checked_wav_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            manifest, row, target = self.fixture(base)
            _, result = self.tool.checked_inputs(target, 'voice')
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0][1], (base / 'clip.wav').resolve())
            self.assertEqual((base / 'clip.wav').read_bytes(), b'unit fixture, never sent to an ASR engine')

    def test_hash_mismatch_rejected_before_model_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _, _, target = self.fixture(base)
            (base / 'clip.wav').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'hash/size'):
                self.tool.checked_inputs(target, 'voice')

    def test_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            manifest, row, target = self.fixture(base)
            row['wav']['path'] = '../outside.wav'
            target.write_text(json.dumps(manifest), 'utf8')
            with self.assertRaisesRegex(ValueError, 'escaped'):
                self.tool.checked_inputs(target, 'voice')

    def test_unknown_source_version_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest, _, target = self.fixture(Path(tmp))
            manifest['source_iso_sha256'] = '0' * 64
            target.write_text(json.dumps(manifest), 'utf8')
            with self.assertRaisesRegex(ValueError, 'supported original-disc'):
                self.tool.checked_inputs(target, 'voice')

    def test_duplicate_id_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest, row, target = self.fixture(Path(tmp))
            manifest['audio'].append(row)
            target.write_text(json.dumps(manifest), 'utf8')
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                self.tool.checked_inputs(target, 'voice')

    def test_unknown_selection_rejected(self):
        with self.assertRaisesRegex(ValueError, 'selection'):
            self.tool.checked_inputs(Path('never-read'), 'guess')


if __name__ == '__main__':
    unittest.main()
