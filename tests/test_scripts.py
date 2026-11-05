import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mysticnights.scripts import ScriptError, extract_strings, patch_strings, protected_tokens


SOURCE = ('SCR_TYPE ITEM\r\n; TEXT "comment"\r\nITEM {\r\n ID 23\r\n'
          ' NAME "회복약(소)"\r\n DESCRIPTION "체력을 30% 회복시켜주는 알약<BR>확인"\r\n'
          ' PASSWORD "ABCD"\r\n}\r\n').encode("cp949")


class ScriptTests(unittest.TestCase):
    def test_scene_room_alias_is_display_but_key_is_protected(self):
        data = 'SCR_TYPE SCENEDEF\nROOM_SPECIFIC {\n ALIAS ROOM17 "연구실"\n ALIAS MONSTER1 "연구실"\n}\n'.encode('cp949')
        rows = extract_strings(data, 'SCENE.SCR')
        self.assertEqual([r.role for r in rows], ['display', 'identifier'])
        changed = patch_strings(data, rows, {rows[0].id: 'Lab'})
        self.assertIn(b'ALIAS ROOM17 "Lab', changed)
        self.assertIn(b'ALIAS MONSTER1', changed)
        self.assertEqual(len(data), len(changed))
        other = extract_strings(data.replace(b'SCENEDEF', b'EVENT'), 'EVENT.SCR')
        self.assertEqual(other[0].role, 'identifier')

    def test_extract_byte_offsets_and_roles(self):
        records = extract_strings(SOURCE, "ITEM.SCR")
        self.assertEqual(len(records), 3)
        self.assertEqual([r.role for r in records], ["display_identifier", "display", "protected"])
        for record in records:
            self.assertEqual(record.source_bytes, SOURCE[record.offset:record.offset+record.capacity])
            self.assertEqual(record.context, "id:23")
            self.assertEqual(record.id, f"ITEM.SCR@{record.offset:08x}")
        self.assertEqual(records[1].tokens, ("<BR>",))

    def test_patch_and_reextract_preserve_size_and_ids(self):
        records = extract_strings(SOURCE, "ITEM.SCR")
        result = patch_strings(SOURCE, records, {records[1].id: "HP 30%<BR>OK"})
        self.assertEqual(len(result), len(SOURCE))
        revised = extract_strings(result, "ITEM.SCR")
        self.assertEqual(revised[1].source, "HP 30%<BR>OK")
        self.assertEqual([r.id for r in revised], [r.id for r in records])
        self.assertEqual(revised[0].source_bytes, records[0].source_bytes)
        self.assertEqual(revised[2].source_bytes, records[2].source_bytes)

    def test_unmodified_round_trip(self):
        records = extract_strings(SOURCE)
        self.assertEqual(patch_strings(SOURCE, records, {}), SOURCE)
        self.assertEqual(patch_strings(SOURCE, records, {r.id:r.source for r in records if r.role == "display"}), SOURCE)

    def test_shared_names_and_passwords_protected(self):
        records = extract_strings(SOURCE)
        for record in (records[0], records[2]):
            with self.assertRaises(ScriptError):
                patch_strings(SOURCE, records, {record.id:"OK"})

    def test_failures_leave_input_unchanged(self):
        records = extract_strings(SOURCE)
        key = records[1].id
        targets = ["no tag", "a" * 100 + "<BR>", 'quote"<BR>', "\r<BR>", "\0<BR>", ""]
        for target in targets:
            with self.subTest(target=target), self.assertRaises(ScriptError):
                patch_strings(SOURCE, records, {key: target})
        self.assertEqual(SOURCE, SOURCE[:])
        with self.assertRaises(ScriptError):
            patch_strings(SOURCE, records, {"absent":"OK"})

    def test_custom_encoder_and_source_guard(self):
        records = extract_strings(SOURCE)
        record = records[1]
        result = patch_strings(SOURCE, records, {record.id:"中文<BR>"}, encode=lambda text:text.encode("utf-8"))
        self.assertIn("中文<BR>".encode(), result)
        changed = bytearray(SOURCE)
        changed[record.offset] = 65
        with self.assertRaises(ScriptError):
            patch_strings(bytes(changed), records, {record.id:"OK<BR>"})
        with self.assertRaises(ScriptError):
            patch_strings(SOURCE, records, {record.id:"OK<BR>"}, encode=lambda _:b'a"b')

    def test_comment_and_empty_fields(self):
        data = b'SCR_TYPE EVENT\r\n;"broken comment\r\n TEXT "A;B" 12 ; "ignored"\r\n TEXT "" 4\r\n'
        records = extract_strings(data)
        self.assertEqual([r.source for r in records], ["A;B", ""])
        self.assertEqual(patch_strings(data, records, {records[1].id:""}), data)

    def test_malformed_scripts(self):
        for data in (b"missing", b'SCR_TYPE \n', b'SCR_TYPE EVENT EXTRA\n', b'SCR_TYPE EVENT\nTEXT "unterminated\n', b'SCR_TYPE EVENT\nTEXT "\xff"\n', b'SCR_TYPE EVENT\nTEXT "A\0B"\n'):
            with self.subTest(data=data), self.assertRaises(ScriptError):
                extract_strings(data)

    def test_nul_then_space_padding_preserved_on_no_op(self):
        data = b'SCR_TYPE EVENT\nTEXT "Hello\0   " 10\n'
        records = extract_strings(data)
        self.assertEqual(records[0].source, "Hello")
        self.assertEqual(patch_strings(data, records, {records[0].id:"Hello"}), data)

    def test_protected_token_order(self):
        text = 'HP 30% %s: %02d<BR>{0}\\n$n'
        self.assertEqual(protected_tokens(text), ("%s", "%02d", "<BR>", "{0}", "\\n", "$n"))
        data = b'SCR_TYPE EVENT\nTEXT "%s %d" 10\n'
        records = extract_strings(data)
        with self.assertRaises(ScriptError):
            patch_strings(data, records, {records[0].id:"%d %s"})

    def test_exact_capacity_and_one_byte_overflow(self):
        data = b'SCR_TYPE EVENT\nTEXT "1234" 10\n'
        records = extract_strings(data)
        self.assertIn(b'"abcd"', patch_strings(data, records, {records[0].id:"abcd"}))
        with self.assertRaises(ScriptError):
            patch_strings(data, records, {records[0].id:"abcde"})

    def test_duplicate_overlapping_and_invalid_encoder(self):
        data = b'SCR_TYPE EVENT\nTEXT "ABCD" 10\n'
        records = extract_strings(data)
        with self.assertRaises(ScriptError):
            patch_strings(data, records*2, {})
        second = replace(records[0], id="different-id")
        with self.assertRaises(ScriptError):
            patch_strings(data, [records[0],second], {records[0].id:"abc", second.id:"abc"})
        with self.assertRaises(ScriptError):
            patch_strings(data, records, {records[0].id:"abc"}, encode=lambda _:"not bytes")
        with self.assertRaises(ScriptError):
            patch_strings(data, records, {records[0].id:"abc"}, padding=b"xx")


if __name__ == "__main__":
    unittest.main()
