from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from extract_auxiliary_text import nul_candidates, extract_auxiliary


class AuxiliaryTests(unittest.TestCase):
    def test_encoding_filter_and_terminated_fields_only(self):
        data = b"English\0" + "확인".encode("utf8") + b"\0\xff\0tail"
        rows = list(nul_candidates(data, "utf-8", [(0xAC00, 0xD7A3)]))
        self.assertEqual(rows, [(8, "확인".encode("utf8"), "확인")])

    def test_no_embedded_control_or_unterminated_tail(self):
        self.assertEqual(list(nul_candidates(b"a\x01b\0tail", "ascii")), [])
        self.assertEqual(list(nul_candidates(b"a\nb\0", "ascii")), [(0, b"a\nb", "a\nb")])

    def test_explicit_source_guard_and_discovery_state(self):
        class Image:
            def read(self, _): return b"\0Hello\0"
        spec = {"sources": [{"resource": "SAMPLE", "encoding": "ascii", "layout": "explicit-slots",
                             "slots": [{"offset": 1, "source": "Hello"}]}]}
        row = extract_auxiliary(Image(), spec)[0]["entries"][0]
        self.assertFalse(row["patch_ready"])
        spec["sources"][0]["slots"][0]["source"] = "Wrong"
        with self.assertRaisesRegex(ValueError, "mismatch"):
            extract_auxiliary(Image(), spec)


if __name__ == "__main__":
    unittest.main()
