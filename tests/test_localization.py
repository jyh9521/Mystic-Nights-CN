import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mysticnights.localization import load_catalogue


class CatalogueTests(unittest.TestCase):
    def run_catalogue(self, data):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalogue.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return load_catalogue(path)

    def setUp(self):
        self.row = {"id": "SAMPLE@00000010", "resource": "SAMPLE", "offset": 16, "capacity": 9,
                    "kind": "elf", "role": "display", "status": "draft", "text_type": "ui_label",
                    "source": "Original", "target": "Translation"}

    def test_valid(self):
        data = {"profile": "poc", "entries": [self.row]}
        self.assertEqual(self.run_catalogue(data), data)

    def test_empty_and_duplicate(self):
        for entries in ([], [self.row, self.row]):
            with self.assertRaises(ValueError):
                self.run_catalogue({"profile": "poc", "entries": entries})

    def test_reject_release_and_protected_role(self):
        for data in ({"profile": "full", "entries": [self.row]},
                     {"profile": "poc", "entries": [{**self.row, "role": "identifier"}]}):
            with self.assertRaises(ValueError):
                self.run_catalogue(data)

    def test_missing_target(self):
        for target in ("", "  ", None):
            with self.assertRaises(ValueError):
                self.run_catalogue({"profile": "poc", "entries": [{**self.row, "target": target}]})

    def test_same_script_slot_cannot_silently_replace_itself(self):
        row = {**self.row, "id": "SAMPLE:EVENT.SCR@00000010", "kind": "script", "member": "EVENT.SCR",
               "script_id": "EVENT.SCR@00000010"}
        self.run_catalogue({"profile": "poc", "entries": [row]})
        with self.assertRaisesRegex(ValueError, "Duplicate physical"):
            self.run_catalogue({"profile": "poc", "entries": [row, {**row, "id": "forged", "target": "Other"}]})

    def test_reject_noncanonical_ids_and_bad_offsets(self):
        for replacement in ({"id": "forged"}, {"offset": True}, {"offset": -1}, {"capacity": 0}):
            with self.assertRaises(ValueError):
                self.run_catalogue({"profile": "poc", "entries": [{**self.row, **replacement}]})


if __name__ == "__main__":
    unittest.main()
