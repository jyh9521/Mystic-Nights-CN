"""Offline verifier source binding and CLI tests; no game/font is required."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import verify_build


class VerificationFontTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.font = b"synthetic font bytes used only for source identity tests"
        self.digest = hashlib.sha256(self.font).hexdigest()
        self.manifest = {"locale": "xx", "font": {"sha256": self.digest}}
        self.config = {"locale": "xx", "font_spec": "assets/selected-font.json"}
        self.spec = {"filename": "fixture.otf", "sha256": self.digest}
        patcher = patch.object(verify_build, "ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_json(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf8")

    def write_default(self, *, font=True):
        self.write_json("locales/xx/config.json", self.config)
        self.write_json("assets/selected-font.json", self.spec)
        if font:
            path = self.root / "build/fonts/fixture.otf"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self.font)

    def test_default_uses_locale_selected_spec_and_manifest_hash(self):
        self.write_default()
        self.write_json("assets/font-source.json", {"filename": "wrong.otf", "sha256": "0" * 64})
        self.assertEqual(verify_build.verification_font_path(self.manifest),
                         self.root / "build/fonts/fixture.otf")

    def test_default_spec_hash_must_match_manifest_before_opening_font(self):
        self.spec["sha256"] = "0" * 64
        self.write_default(font=False)
        with self.assertRaisesRegex(ValueError, "Font source configuration/manifest hash mismatch"):
            verify_build.verification_font_path(self.manifest)

    def test_default_and_override_files_must_match_manifest_hash(self):
        self.write_default()
        path = self.root / "build/fonts/fixture.otf"
        path.write_bytes(b"unexpected font")
        for override in (None, path):
            with self.subTest(override=override), self.assertRaisesRegex(ValueError, "Verification font hash mismatch"):
                verify_build.verification_font_path(self.manifest, override)

    def test_override_needs_no_default_cache_or_configuration(self):
        path = self.root / "external.otf"
        path.write_bytes(self.font)
        self.assertEqual(verify_build.verification_font_path(self.manifest, path), path)
        self.assertFalse((self.root / "locales").exists())
        self.assertFalse((self.root / "build").exists())

    def test_invalid_manifest_hash_and_locale_are_rejected(self):
        for digest in (None, 0, "a" * 63, "z" * 64):
            with self.subTest(digest=digest), self.assertRaisesRegex(ValueError, "Invalid manifest font hash"):
                verify_build.verification_font_path({"locale": "xx", "font": {"sha256": digest}})
        for locale in (None, "", "../xx", "x/x", "x\\x"):
            with self.subTest(locale=locale), self.assertRaisesRegex(ValueError, "Invalid manifest locale"):
                verify_build.verification_font_path({**self.manifest, "locale": locale})

    def test_mismatched_locale_and_escaping_default_paths_are_rejected(self):
        self.config["locale"] = "yy"
        self.write_default(font=False)
        with self.assertRaisesRegex(ValueError, "Font locale configuration mismatch"):
            verify_build.verification_font_path(self.manifest)
        self.config["locale"] = "xx"
        for name in ("../escape.json", str(self.root / "outside.json")):
            self.config["font_spec"] = name
            self.write_default(font=False)
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "Font source configuration escapes repository"):
                verify_build.verification_font_path(self.manifest)
        self.config["font_spec"] = "assets/selected-font.json"
        for filename in ("../escape.otf", "nested/font.otf", str(self.root / "outside.otf")):
            self.spec["filename"] = filename
            self.write_default(font=False)
            with self.subTest(filename=filename), self.assertRaisesRegex(ValueError, "Invalid configured font filename"):
                verify_build.verification_font_path(self.manifest)

    def test_cli_passes_explicit_font_to_modified_verifier(self):
        self.write_json("manifest.json", {"original": {"size": 1, "sha256": "0" * 64}})
        original, output = object(), object()
        for override in (None, self.root / "external.otf"):
            argv = ["verify_build.py", "--kind", "modified", "--original", "original.iso",
                    "--iso", "modified.iso", "--manifest", str(self.root / "manifest.json")]
            if override is not None:
                argv += ["--font", str(override)]
            with self.subTest(override=override), patch.object(sys, "argv", argv), \
                 patch.object(verify_build, "load_version", return_value={"iso": {"size": 1, "sha256": "0" * 64}}), \
                 patch.object(verify_build, "verify_original", return_value=original), \
                 patch.object(verify_build, "IsoImage", return_value=output), \
                 patch.object(verify_build, "modified") as modified:
                verify_build.main()
                modified.assert_called_once_with(original, output, {"original": {"size": 1, "sha256": "0" * 64}},
                                                 font_path=override)

    def test_modified_passes_font_to_full_paths(self):
        image = SimpleNamespace(path=Path("synthetic.iso"), size=1, files={}, directories={})
        manifest = {"modified": {"sha256": "0" * 64, "size": 1}, "entries": [],
                    "font": {"mapping": {}}, "full_text": {"synthetic": True}}
        override = self.root / "external.otf"
        with patch.object(verify_build, "sha256_file", return_value="0" * 64), \
             patch.object(verify_build, "verify_full_paths", side_effect=RuntimeError("full path reached")) as full:
            with self.assertRaisesRegex(RuntimeError, "full path reached"):
                verify_build.modified(image, image, manifest, font_path=override)
            full.assert_called_once_with(image, image, manifest, {"RES/SYSTEM.RES": []}, font_path=override)

    def test_graphics_rerender_receives_override_and_binds_catalogue_font(self):
        path = self.root / "external.otf"
        path.write_bytes(self.font)
        resources = {"NETGUICD.ELF": b"network", "NETGUI/KOREAN.PF": b"pf", "DATA/AGREE.TXT": b"agreement"}
        image = SimpleNamespace(read=resources.__getitem__)
        report = {"installed_slots": [], "pending_art_restoration_slots": [], "changed_texture_members": 0}
        graphics = {"recipe": {"textures": []}, "catalogue": {"font_sha256": self.digest, "entries": []},
                    "report": report}
        manifest = {**self.manifest, "font": {**self.manifest["font"], "mapping": {}}, "full_text": {
            "name_links_sha256": "links", "names": [],
            "auxiliary": {"network": [], "agreement": [], "extra_interface": []},
            "network_font": {"protected_codepoints": [], "source_sha256": hashlib.sha256(b"pf").hexdigest(),
                             "mapping": {}, "changed_glyphs": []}, "graphics": graphics}}
        with patch("mysticnights.linked_names.discover_name_links", return_value={"core_sha256": "links", "groups": []}), \
             patch("mysticnights.network_font.collect_protected_codepoints", return_value=set()), \
             patch("mysticnights.network_font.parse_pf", return_value=SimpleNamespace(subfonts=(), glyphs={})), \
             patch("mysticnights.network_font.allocate_mapping", return_value={}), \
             patch("mysticnights.graphics.build_graphics", return_value=({}, report)) as build, patch("builtins.print"):
            verify_build.verify_full_paths(image, image, manifest, {}, font_path=path)
            build.assert_called_once_with(image, graphics["recipe"], graphics["catalogue"], path)
            build.reset_mock()
            graphics["catalogue"]["font_sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "Graphics/manifest font hash mismatch"):
                verify_build.verify_full_paths(image, image, manifest, {}, font_path=path)
            build.assert_not_called()


if __name__ == "__main__":
    unittest.main()
