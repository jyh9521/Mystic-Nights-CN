import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))
from mysticnights.catalogues import read_project
from mysticnights.localization import load_catalogue
from validate_translations import validate_project


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.index = {"format": "localization-catalogue", "version": 1, "profile": "partial",
                      "locale": "xx", "files": ["dialogue.json"]}
        self.row = {"id": "SAMPLE:EVENT.SCR@00000010", "resource": "SAMPLE", "kind": "script",
                    "member": "EVENT.SCR", "script_id": "EVENT.SCR@00000010", "offset": 16,
                    "capacity": 8, "source": "Original", "target": "Target", "status": "draft",
                    "role": "display", "text_type": "dialogue"}

    def tearDown(self):
        self.temp.cleanup()

    def write(self, rows, index=None, locale="xx"):
        (self.root / "catalogue.json").write_text(json.dumps(index or self.index), encoding="utf8")
        (self.root / "dialogue.json").write_text(json.dumps({"locale": locale, "entries": rows}), encoding="utf8")
        return self.root / "catalogue.json"

    def test_only_explicit_drafts_selected(self):
        pending = {**self.row, "id": "pending", "status": "untranslated", "target": ""}
        blank = {**self.row, "id": "blank", "status": "non_text", "target": " ", "source": " "}
        result = read_project(self.write([self.row, pending, blank]))
        self.assertEqual(result["entries"], [self.row])
        self.assertEqual(result["coverage"]["states"], {"draft": 1, "untranslated": 1, "non_text": 1})
        self.assertEqual(len(result["catalogue_files_sha256"]["dialogue.json"]), 64)

    def test_mirror_expands_from_one_target(self):
        row = {**self.row, "id": "RES/UI/ITEM.RES:DOCUMENT.SCR@00000010",
               "resource": "RES/UI/ITEM.RES", "member": "DOCUMENT.SCR", "script_id": "DOCUMENT.SCR@00000010",
               "text_type": "document", "mirrored_resources": ["RES/UI/DOCUMENT.RES"]}
        result = load_catalogue(self.write([row]))
        self.assertEqual(len(result["entries"]), 2)
        self.assertEqual(result["entries"][1]["id"], "RES/UI/DOCUMENT.RES:DOCUMENT.SCR@00000010")
        self.assertEqual(result["entries"][0]["target"], result["entries"][1]["target"])

    def test_no_arbitrary_mirror(self):
        with self.assertRaisesRegex(ValueError, "mirror"):
            read_project(self.write([{**self.row, "mirrored_resources": ["UNKNOWN.RES"]}]))

    def test_missing_or_empty_document_mirror_rejected(self):
        row = {**self.row, "id": "RES/UI/ITEM.RES:DOCUMENT.SCR@00000010",
               "resource": "RES/UI/ITEM.RES", "member": "DOCUMENT.SCR", "script_id": "DOCUMENT.SCR@00000010"}
        for candidate in (row, {**row, "mirrored_resources": []}):
            with self.assertRaisesRegex(ValueError, "required document mirror"):
                read_project(self.write([candidate]))

    def test_reject_paths_duplicates_and_locale_mismatch(self):
        for files in (["../outside.json"], [str(self.root / "dialogue.json")], ["dialogue.json"] * 2, ["catalogue.json"]):
            with self.assertRaises(ValueError):
                read_project(self.write([self.row], {**self.index, "files": files}))
        with self.assertRaisesRegex(ValueError, "locale"):
            read_project(self.write([self.row], locale="yy"))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            read_project(self.write([self.row, self.row]))

    def test_pending_target_and_fake_nontext_rejected(self):
        for row in ({**self.row, "status": "untranslated"}, {**self.row, "status": "non_text"},
                    {**self.row, "status": "draft", "target": ""}):
            with self.assertRaises(ValueError):
                read_project(self.write([row]))

    def test_candidate_is_not_auto_promoted(self):
        with self.assertRaisesRegex(ValueError, "role"):
            load_catalogue(self.write([{**self.row, "role": "candidate_display"}]))

    def test_full_text_rejects_any_untranslated_field(self):
        index = {**self.index, "profile": "full-text"}
        self.assertEqual(load_catalogue(self.write([self.row], index))["profile"], "full-text")
        pending = {**self.row, "id": "pending", "status": "untranslated", "target": ""}
        with self.assertRaisesRegex(ValueError, "untranslated"):
            load_catalogue(self.write([self.row, pending], index))


class TranslationDataTests(unittest.TestCase):
    def test_locale_is_consistent(self):
        report = validate_project(ROOT / "locales/zh-CN")
        self.assertEqual(report["canonical_item_names"], 113)
        self.assertEqual(report["logical_catalogue_fields"], 2036)
        self.assertGreaterEqual(report["selected_physical_fields"], 340)
        self.assertEqual(report["states"], {"draft": 2034, "non_text": 2})
        self.assertEqual(report["selected_physical_fields"], 2126)
        self.assertEqual(report["auxiliary_translated_fields"], {"network": 270, "agreement": 1, "extra_interface": 38})

    def test_opening_and_item_batch_not_fragmented(self):
        directory = ROOT / "locales/zh-CN/text"
        rows = json.loads((directory / "dialogue.json").read_text(encoding="utf8"))["entries"]
        first = [r for r in rows if 10 <= int(r["context"].split(":")[1]) <= 67]
        self.assertEqual(len(first), 114)
        self.assertTrue(all(r["status"] in {"draft", "reviewed"} for r in first))
        items = json.loads((directory / "items.json").read_text(encoding="utf8"))["entries"]
        self.assertEqual(len(items), 190)
        self.assertTrue(all(r["status"] in {"draft", "reviewed", "non_text"} for r in items))

    def test_document_mirrors_and_original_page_boundaries(self):
        rows = json.loads((ROOT / "locales/zh-CN/text/documents.json").read_text(encoding="utf8"))["entries"]
        self.assertEqual(len(rows), 92)
        self.assertTrue(all(r["mirrored_resources"] == ["RES/UI/DOCUMENT.RES"] for r in rows))
        self.assertEqual(sum(r["status"] == "draft" for r in rows), 92)


if __name__ == "__main__":
    unittest.main()
