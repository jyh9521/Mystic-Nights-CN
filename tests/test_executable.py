import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mysticnights.executable import patch_strings, validate_tokens


class ExecutableTests(unittest.TestCase):
    def setUp(self):
        self.original = b"\x7fELF\x01\x01" + b"\0" * 10 + "확인".encode("cp949") + b"\0" + b"unchanged"
        self.entry = {"id": "test", "offset": 16, "capacity": 5, "source": "확인", "target": "OK"}

    def test_exact_slot_and_suffix(self):
        result = patch_strings(self.original, [self.entry], str.encode)
        self.assertEqual(result[16:21], b"OK\0\0\0")
        self.assertEqual(result[:16], self.original[:16])
        self.assertEqual(result[21:], self.original[21:])
        self.assertEqual(len(result), len(self.original))

    def test_wrong_source(self):
        with self.assertRaisesRegex(ValueError, "mismatch"):
            patch_strings(self.original, [{**self.entry, "source": "문서"}], str.encode)

    def test_overflow(self):
        with self.assertRaisesRegex(ValueError, "overflow"):
            patch_strings(self.original, [{**self.entry, "target": "TOOLONG"}], str.encode)

    def test_duplicate_id(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            patch_strings(self.original, [self.entry, self.entry], str.encode)

    def test_tokens(self):
        validate_tokens("%s: %02d <O>", "%s: %02d<BR><O>")
        for target in ("%s: %d <O>", "%02d: %s <O>", "%s: %02d", "%s: %02d <O>\0", "%s: %02d <O> %n", "%s: %02d <O> %*s"):
            with self.assertRaises(ValueError):
                validate_tokens("%s: %02d <O>", target)

    def test_dynamic_printf_fields(self):
        validate_tokens("%*.*s %lld %%", "%*.*s %lld %%")
        for target in ("%s", "%*s", "%.*s", "%n"):
            with self.assertRaises(ValueError):
                validate_tokens("确认", target)


if __name__ == "__main__":
    unittest.main()
