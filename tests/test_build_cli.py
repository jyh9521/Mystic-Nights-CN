"""Transaction/release-gate tests use no game, font or emulator input."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_locale


class BuildCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.output = self.root / "output"
        locale = self.root / "locales/xx"
        locale.mkdir(parents=True)
        (self.root / "assets").mkdir()
        self.write("locales/xx/config.json", {"locale": "xx", "translations": "poc.json", "font_spec": "assets/font.json",
                                             "font_pixel_size": 13})
        self.write("locales/xx/poc.json", {"locale": "xx", "profile": "poc", "entries": [
            {"id": "SAMPLE@00000010", "resource": "SAMPLE", "offset": 16, "capacity": 5,
             "kind": "elf", "role": "display", "status": "draft", "text_type": "ui_label", "source": "Text", "target": "Test"}]})
        self.write("assets/game-version.json", {"iso": {"size": 16, "sha256": "0" * 64}})
        self.write("assets/elf-text-slots.json", {})
        self.write("assets/font.json", {"name": "Synthetic", "filename": "fixture.otf"})

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, relative, value):
        (self.root / relative).write_text(json.dumps(value), encoding="utf-8")

    def test_patch_failure_removes_only_transaction(self):
        original = self.root / "original.iso"
        original.write_bytes(b"original")
        font = SimpleNamespace(font_sha256="1" * 64, mapping={}, fnt=b"", textures={})
        def write_iso(source, output, replacements, **kwargs):
            output.write_bytes(b"synthetic")
            return {"size": 16, "sha256": "2" * 64, "replacements": []}
        args = ["build_locale.py", "--iso", str(original), "--locale", "xx", "--output", str(self.output)]
        with patch.object(build_locale, "ROOT", self.root), patch.object(sys, "argv", args), \
             patch.object(build_locale, "verify_original", return_value=object()), \
             patch.object(build_locale, "localized_resources", return_value=({}, font, [])), \
             patch.object(build_locale, "replace_files", side_effect=write_iso), \
             patch.object(build_locale, "build_patch", side_effect=OSError("injected patch failure")):
            with self.assertRaisesRegex(OSError, "injected"):
                build_locale.main()
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob(".output-*")), [])
        self.assertEqual(original.read_bytes(), b"original")

    def test_release_gate_precedes_output(self):
        args = ["build_locale.py", "--iso", "unused.iso", "--release", "--output", str(self.output)]
        with patch.object(sys, "argv", args), patch("sys.stderr"):
            with self.assertRaises(SystemExit) as result:
                build_locale.main()
        self.assertEqual(result.exception.code, 2)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
