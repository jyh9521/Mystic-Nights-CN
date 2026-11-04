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

    def test_button_tokens_keep_order_not_only_counts(self):
        validate_tokens("<O> yes <X> no", "<O>是<BR><X>否")
        with self.assertRaisesRegex(ValueError, "control"):
            validate_tokens("<O> yes <X> no", "<X>否<O>是")

    def test_only_explicit_zero_alignment_padding_can_extend_span(self):
        original = b"\x7fELF\x01\x01" + b"\0" * 10 + b"Bruce\0\0\0Next\0"
        row = {"id":"sample","offset":16,"source":"Bruce","target":"abcdef","capacity":7,"padding_bytes":1}
        result = patch_strings(original, [row], str.encode)
        self.assertEqual(result[16:], b"abcdef\0\0Next\0")
        for change in ({"padding_bytes":0}, {"padding_bytes":-1}, {"padding_bytes":True}, {"padding_bytes":16}):
            with self.assertRaises(ValueError):patch_strings(original,[{**row,**change}],str.encode)
        changed = original[:22] + b"X" + original[23:]
        with self.assertRaisesRegex(ValueError,"original bytes"):
            patch_strings(changed,[row],str.encode)


if __name__ == "__main__":
    unittest.main()
