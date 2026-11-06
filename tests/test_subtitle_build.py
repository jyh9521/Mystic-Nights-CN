"""Explicit cutscene opt-in and font input seams; no game execution."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_locale
import verify_build
from mysticnights.cutscene_subtitles import validate_catalogue, ORIGINAL_ISO_SHA256
from mysticnights.localization import localized_resources


class SubtitleGateTests(unittest.TestCase):
    def test_complete_inventory_with_no_reviewed_cues_does_not_enable_feature(self):
        source = {'scene': 'C001', 'resource': 'RES/C001.RES', 'member': 'C001.SCR', 'source_sha256': 'a' * 64,
                  'source_size': 1000, 'camera_sha256': 'b' * 64, 'camera_frames': 100,
                  'camera_resource': 'RES/C001.RES', 'camera_member': 'C001.BIN'}
        catalogue = {'format': 'cutscene-subtitle-catalogue', 'version': 1, 'locale': 'xx',
                     'source_iso_sha256': ORIGINAL_ISO_SHA256, 'resources': [{**source, 'cues': []}]}
        with patch('mysticnights.cutscene_subtitles.inventory', return_value=[source]):
            with self.assertRaisesRegex(ValueError, 'no reviewed cues'):
                validate_catalogue(object(), catalogue, locale='xx')
            catalogue['locale'] = 'yy'
            with self.assertRaisesRegex(ValueError, 'locale mismatch'):
                validate_catalogue(object(), catalogue, locale='xx')

    def test_explicit_catalogue_identity_requires_compiled_feature(self):
        with self.assertRaisesRegex(ValueError, 'not compiled'):
            verify_build.verify_cutscene_subtitles(object(), object(), {'full_text': {}}, {}, catalogue_path=Path('unused.json'))

    def test_builder_rejects_asr_before_font_generation_and_output(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); (root / 'assets').mkdir(); (root / 'locales/xx').mkdir(parents=True)
            documents = {
                'locales/xx/config.json': {'locale': 'xx', 'translations': 'poc.json', 'font_spec': 'assets/font.json', 'font_pixel_size': 13},
                'locales/xx/poc.json': {'locale': 'xx', 'profile': 'full-text', 'entries': [
                    {'id': 'SAMPLE@00000000', 'resource': 'SAMPLE', 'kind': 'elf', 'offset': 0, 'capacity': 5,
                     'source': 'Text', 'target': 'Test', 'role': 'display', 'status': 'draft', 'text_type': 'ui_label'}]},
                'assets/font.json': {'name': 'Synthetic', 'filename': 'fixture.otf'},
                'assets/game-version.json': {'iso': {'size': 1, 'sha256': '0' * 64}},
                'assets/elf-text-slots.json': {},
                'subtitle.json': {'format': 'cutscene-subtitle-catalogue', 'status': 'asr-draft'},
            }
            for relative, value in documents.items():
                (root / relative).write_text(json.dumps(value), 'utf8')
            output = root / 'output'
            args = ['build_locale.py', '--iso', 'fixture.iso', '--locale', 'xx', '--output', str(output),
                    '--subtitle-catalog', str(root / 'subtitle.json')]
            with patch.object(build_locale, 'ROOT', root), patch.object(sys, 'argv', args), \
                    patch.object(build_locale, 'verify_original', return_value=object()), \
                    patch('mysticnights.cutscene_subtitles.validate_catalogue', side_effect=ValueError('asr-draft rejected')), \
                    patch.object(build_locale, 'localized_resources') as resources:
                with self.assertRaisesRegex(ValueError, 'asr-draft rejected'):
                    build_locale.main()
                resources.assert_not_called()
            self.assertFalse(output.exists())
            self.assertEqual(list(root.glob('.output-*')), [])

    def test_additional_font_input_is_generic_and_does_not_forge_string_slots(self):
        image = SimpleNamespace(read=lambda _: b'original', get=lambda _: SimpleNamespace(size=8))
        archive = SimpleNamespace(read=lambda _: b'font', replace=lambda _: b'original')
        font = SimpleNamespace(mapping={}, textures={})
        entries = [{'id': 'SAMPLE@00000000', 'resource': 'SAMPLE', 'kind': 'elf', 'offset': 0,
                    'capacity': 5, 'source': 'Text', 'target': 'Test', 'text_type': 'ui_label'}]
        config = {'font_allowed_codes': {'first': 0xA4A1, 'last': 0xA4FE}, 'font_pixel_size': 13}
        with patch('mysticnights.localization.parse_res', return_value=archive), \
                patch('mysticnights.localization.retained_codes', return_value=set()), \
                patch('mysticnights.localization.build_font', return_value=font) as build, \
                patch('mysticnights.localization.patch_executable', return_value=b'original'):
            localized_resources(image, {'profile': 'poc', 'entries': entries}, config, {'sha256': 'a' * 64},
                                Path('unused.otf'), {'resource': 'SAMPLE', 'entries': entries}, additional_font_texts=['caption literal 100%'])
            self.assertEqual(build.call_args.args[2], ['Test', 'caption literal 100%'])
            self.assertEqual(len(entries), 1)


if __name__ == '__main__':
    unittest.main()
