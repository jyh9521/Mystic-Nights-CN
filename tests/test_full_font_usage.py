"""Synthetic replacement-bound full-font tests; no original assets required."""
import copy
import hashlib
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mysticnights.font_usage import (_ReplacementRegistry, collect_full_protected_codes,
                                    digest, MAIN_ELF, AUXILIARY_ELF)
from mysticnights.resources import MAGIC, parse_res
from mysticnights.scripts import extract_strings


def archive_fixture(members):
    out = bytearray(MAGIC)
    for group in range(8):
        selected = members if group == 5 else []
        out += struct.pack("<I", len(selected))
        for name, body in selected:
            out += name.encode("cp949").ljust(32, b"\0")
            out += struct.pack("<I", len(body)) + body
    return bytes(out)


def elf_fixture(body):
    out = bytearray(84)
    out[:7] = b"\x7fELF\x01\x01\x01"
    struct.pack_into("<H", out, 18, 8)
    struct.pack_into("<I", out, 28, 52)
    struct.pack_into("<HH", out, 42, 32, 1)
    struct.pack_into("<8I", out, 52, 1, 84, 0x100000, 0x100000, len(body), len(body), 7, 4)
    return bytes(out) + body


def code(char):
    return int.from_bytes(char.encode("cp949"), "big")


class ImageFixture:
    def __init__(self, script='SCR_TYPE EVENT\nEVENT_ID 1\nTEXT "가"\n', elf_body=b"ASCII\0"):
        self.files = {
            "RES/SYSTEM.RES": archive_fixture([("FONT.FNT", b"font-fixture")]),
            "RES/SUBSYS.RES": archive_fixture([("EVENT.SCR", script.encode("cp949"))]),
            MAIN_ELF: elf_fixture(elf_body), AUXILIARY_ELF: elf_fixture("다".encode("cp949") + b"\0"),
            "SYSTEM.CNF": b"BOOT = cdrom0:\\SCKA_200.55;1\r\n",
        }

    def read(self, path):
        return self.files[path]

    def get(self, path):
        return SimpleNamespace(offset=0, size=len(self.files[path]))


FONT = [SimpleNamespace(code=key) for key in [*range(32, 127), *range(0xA4A1, 0xA4FF),
        *(lead * 256 + trail for lead in range(0xB0, 0xC9) for trail in range(0xA1, 0xFF))]]
VERSION = {"iso": {"size": 1234, "sha256": "1" * 64}, "files": {}}


def script_row(image, index=0, target="中", resource="RES/SUBSYS.RES", member="EVENT.SCR"):
    payload = parse_res(image.read(resource)).read(member)
    record = [r for r in extract_strings(payload, member) if r.role == "display"][index]
    return {"id": f"{resource}:{record.id}", "kind": "script", "resource": resource, "member": member,
            "script_id": record.id, "offset": record.offset, "capacity": record.capacity,
            "source": record.source, "source_sha256": record.source_sha256,
            "role": "display", "status": "draft", "target": target}


def elf_row(source="가", target="中", offset=84):
    raw = source.encode("cp949") + b"\0"
    return {"id": f"{MAIN_ELF}@{offset:08x}", "resource": MAIN_ELF, "kind": "elf", "role": "display",
            "status": "draft", "offset": offset, "capacity": len(raw), "source": source,
            "source_sha256": digest(raw), "target": target}


class FullFontUsageTests(unittest.TestCase):
    def survey(self, image, entries=(), **kwargs):
        before = copy.deepcopy(image.files)
        with patch("mysticnights.font_usage.verify_original", return_value=image) as verify, \
                patch("mysticnights.font_usage.parse_fnt", return_value=FONT):
            result = collect_full_protected_codes(Path("synthetic.iso"), VERSION, entries, **kwargs)
        verify.assert_called_once_with(Path("synthetic.iso"), VERSION)
        self.assertEqual(image.files, before)
        self.assertEqual(result[1]["translation_binding"]["iso_sha256"], VERSION["iso"]["sha256"])
        return result

    def test_keeps_actual_display_not_comments_or_logic(self):
        image = ImageFixture('SCR_TYPE EVENT\nEVENT_ID 1\nTEXT "가"\n; 나\nOBJECT "라"\n')
        protected, report = self.survey(image)
        self.assertIn(code("가"), protected)
        self.assertNotIn(code("나"), protected)
        self.assertNotIn(code("라"), protected)
        audit = next(r for r in report["script_non_display_audit"] if r["member"] == "EVENT.SCR")
        self.assertIn(code("나"), audit["complete_plaintext_codes"])
        self.assertIn(code("라"), audit["ignored_quoted_field_codes"])

    def test_source_is_released_only_when_every_display_occurrence_changes(self):
        image = ImageFixture('SCR_TYPE EVENT\nEVENT_ID 1\nTEXT "가"\nTEXT "가"\n')
        row = script_row(image)
        self.assertIn(code("가"), self.survey(image, [row])[0])
        protected, report = self.survey(image, [row, script_row(image, 1)])
        self.assertNotIn(code("가"), protected)
        self.assertEqual(report["counts"]["replaced_display_fields"], 2)

    def test_catalogue_source_hash_capacity_and_identity_are_checked(self):
        image = ImageFixture()
        for field, value in (("source_sha256", "0" * 64), ("capacity", 99), ("source", "나"),
                             ("id", "not-canonical"), ("role", "item_reference"), ("status", "untranslated")):
            with self.subTest(field=field), self.assertRaises(ValueError):
                row = script_row(image)
                row[field] = value
                self.survey(image, [row])

    def test_duplicate_selected_identity_fails(self):
        image = ImageFixture()
        row = script_row(image)
        with self.assertRaisesRegex(ValueError, "Duplicate selected"):
            self.survey(image, [row, row])

    def test_target_empty_nul_and_overflow_fail(self):
        image = ImageFixture()
        for target in ("", "\0", "中文"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                self.survey(image, [script_row(image, target=target)])

    def test_remaining_main_elf_suffix_after_binary_prefix_is_protected(self):
        body = "가".encode("cp949") + b"\0\xff\x01" + "나".encode("cp949") + b"\0"
        image = ImageFixture(elf_body=body)
        protected, report = self.survey(image, [script_row(image), elf_row()])
        self.assertNotIn(code("가"), protected)
        self.assertIn(code("나"), protected)
        self.assertIn(code("나"), report["tier_codes"]["retained_main_elf_suffixes"])

    def test_same_code_elsewhere_in_elf_is_not_released(self):
        image = ImageFixture(elf_body="가\0가\0".encode("cp949"))
        protected, _ = self.survey(image, [script_row(image), elf_row()])
        self.assertIn(code("가"), protected)

    def test_extra_elf_schema_binds_hash_excluding_terminator(self):
        image = ImageFixture(elf_body="가\0".encode("cp949"))
        row = elf_row()
        row.pop("kind")
        row.pop("capacity")
        row.update(source_bytes=2, source_sha256=digest("가".encode("cp949")), encoding="cp949", patch_ready=True)
        protected, _ = self.survey(image, [script_row(image), row])
        self.assertNotIn(code("가"), protected)
        row["source_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            self.survey(image, [row])

    def test_elf_slot_requires_original_nul_and_load_bounds(self):
        image = ImageFixture(elf_body="가X".encode("cp949"))
        with self.assertRaises(ValueError):
            self.survey(image, [elf_row()])
        image = ImageFixture(elf_body=b"\0")
        image.files[MAIN_ELF] += "가\0".encode("cp949")
        with self.assertRaisesRegex(ValueError, "outside PT_LOAD"):
            self.survey(image, [elf_row(offset=85)])

    def test_normalized_elf_padding_binds_entire_zero_span(self):
        image = ImageFixture(elf_body=b"Frank\0\0NEXT\0")
        row = elf_row(source="Frank", target="弗兰克")
        row.update(padding_bytes=1, capacity=7, source_sha256=digest(b"Frank\0\0"))
        _, report = self.survey(image, [row])
        span = report["translation_binding"]["physical_fields"][0]
        self.assertEqual(span["capacity"], 7)
        self.assertEqual(span["source_sha256"], digest(b"Frank\0\0"))
        row["source_sha256"] = digest(b"Frank\0")
        with self.assertRaisesRegex(ValueError, "hash/capacity"):
            self.survey(image, [row])

    def test_native_extra_padding_requires_exact_zero_bytes(self):
        image = ImageFixture(elf_body=b"Frank\0\0NEXT\0")
        row = elf_row(source="Frank", target="弗兰克")
        row.pop("kind")
        row.pop("capacity")
        row.update(padding_bytes=1, source_bytes=5, source_sha256=digest(b"Frank"),
                   encoding="cp949", patch_ready=True)
        self.survey(image, [row])
        for padding in (-1, True, 1.0, 2):
            with self.subTest(padding=padding), self.assertRaises(ValueError):
                self.survey(image, [{**row, "padding_bytes": padding}])
        image.files[MAIN_ELF] = elf_fixture(b"Frank\0XNEXT\0")
        with self.assertRaises(ValueError):
            self.survey(image, [row])

    def test_complete_plaintext_remains_until_bound_replacement(self):
        image = ImageFixture()
        data = "나<END>\r\n".encode("cp949")
        image.files["DATA/AGREE.TXT"] = data
        self.assertIn(code("나"), self.survey(image)[0])
        binding = {"DATA/AGREE.TXT": {"source_sha256": digest(data), "target": "文<END>\r\n"}}
        protected, _ = self.survey(image, plaintext_replacements=binding)
        self.assertNotIn(code("나"), protected)
        binding["DATA/AGREE.TXT"]["source_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            self.survey(image, plaintext_replacements=binding)

    def test_plaintext_control_and_whole_file_type_are_guarded(self):
        image = ImageFixture()
        data = "나<END>".encode("cp949")
        image.files["DATA/AGREE.TXT"] = data
        with self.assertRaisesRegex(ValueError, "control tokens"):
            self.survey(image, plaintext_replacements={"DATA/AGREE.TXT": {"source_sha256": digest(data), "target": "文"}})
        with self.assertRaisesRegex(ValueError, "Not a complete plaintext"):
            self.survey(image, plaintext_replacements={MAIN_ELF: {"source_sha256": "0" * 64, "target": "文"}})

    def test_netgui_separate_font_not_promoted_to_main_font(self):
        protected, report = self.survey(ImageFixture())
        self.assertNotIn(code("다"), protected)
        separate = report["separate_font_domains"][0]
        self.assertIn(code("다"), separate["cp949_suffix_coincidence_codes"])
        self.assertFalse(separate["use_for_main_font_protection"])

    def test_unknown_binary_candidates_are_reported_not_display_assertions(self):
        image = ImageFixture()
        image.files["RES/OPAQUE.RES"] = archive_fixture([("OBJECT.SCN", b"\0" + "나".encode("cp949") + b"\0")])
        protected, report = self.survey(image)
        self.assertNotIn(code("나"), protected)
        self.assertIn(code("나"), report["unknown_binary_audit"]["members"][0]["candidate_codes"])
        self.assertFalse(report["unknown_binary_audit"]["use_for_automatic_protection"])

    def test_wholly_printable_unknown_member_is_conservatively_retained(self):
        image = ImageFixture()
        image.files["RES/OTHER.RES"] = archive_fixture([("NOTICE.BIN", "나".encode("cp949"))])
        self.assertIn(code("나"), self.survey(image)[0])

    def test_target_change_changes_binding_not_unrelated_protection(self):
        image = ImageFixture()
        left, a = self.survey(image, [script_row(image, target="中")])
        right, b = self.survey(image, [script_row(image, target="文")])
        self.assertEqual(left, right)
        self.assertNotEqual(a["translation_binding_sha256"], b["translation_binding_sha256"])

    def test_document_mirror_is_bound_and_checked(self):
        image = ImageFixture()
        body = archive_fixture([("DOCUMENT.SCR", 'SCR_TYPE DOC\nITEM {\nID 1\nTEXT "나"\n}\n'.encode("cp949"))])
        for name in ("RES/UI/ITEM.RES", "RES/UI/DOCUMENT.RES"):
            image.files[name] = body
        row = script_row(image, resource="RES/UI/ITEM.RES", member="DOCUMENT.SCR")
        row["mirrored_resources"] = ["RES/UI/DOCUMENT.RES"]
        protected, report = self.survey(image, [row])
        self.assertNotIn(code("나"), protected)
        self.assertEqual(report["counts"]["selected_catalogue_physical_fields"], 2)
        image.files["RES/UI/DOCUMENT.RES"] = body.replace("나".encode("cp949"), "다".encode("cp949"))
        with self.assertRaises(ValueError):
            self.survey(image, [row])

    def name_manifest(self):
        raw = "가\0".encode("cp949")
        return {"gaps": [], "core_sha256": "2" * 64, "groups": [{
            "id": "id:1", "source": "가", "source_text_sha256": digest(raw[:-1]), "max_encoded_bytes": 2,
            "references": [{"resource": MAIN_ELF, "offset": 84, "expected_hex": raw.hex(),
                            "capacity": 3, "source_sha256": digest(raw), "kind": "elf", "capacity_includes_nul": True}],
        }]}

    def test_elf_name_and_catalogue_overlap_require_same_target(self):
        image = ImageFixture(elf_body="가\0".encode("cp949"))
        with patch("mysticnights.linked_names.discover_name_links", return_value=self.name_manifest()):
            _, report = self.survey(image, [elf_row()], name_targets={"id:1": "中"})
            fields = report["translation_binding"]["physical_fields"]
            self.assertEqual(len(fields), 1)
            self.assertEqual(len(fields[0]["aliases"]), 2)
            with self.assertRaisesRegex(ValueError, "Conflicting replacement"):
                self.survey(image, [elf_row()], name_targets={"id:1": "文"})

    def test_unchanged_name_target_keeps_original_font_codes(self):
        image = ImageFixture(elf_body="가\0".encode("cp949"))
        with patch("mysticnights.linked_names.discover_name_links", return_value=self.name_manifest()):
            protected, report = self.survey(image, [script_row(image)], name_targets={"id:1": "가"})
            self.assertIn(code("가"), protected)
            self.assertEqual(report["counts"]["unique_replaced_ranges"], 1)

    def test_unknown_names_and_gaps_fail_closed(self):
        image = ImageFixture()
        manifest = self.name_manifest()
        with patch("mysticnights.linked_names.discover_name_links", return_value=manifest):
            with self.assertRaises(ValueError):
                self.survey(image, name_targets={"id:2": "文"})
            manifest["gaps"] = [{"kind": "unresolved"}]
            with self.assertRaises(ValueError):
                self.survey(image, name_targets={"id:1": "文"})

    def test_registry_rejects_partial_overlap_and_changed_bytes(self):
        registry = _ReplacementRegistry()
        data = b"ABCD\0"
        registry.add("test", data, 0, data, "X", "one", "elf", includes_nul=True)
        with self.assertRaisesRegex(ValueError, "Partially overlapping"):
            registry.add("test", data, 1, data[1:], "Y", "two", "elf", includes_nul=True)
        with self.assertRaisesRegex(ValueError, "source bytes differ"):
            registry.add("other", data, 0, b"bad", "X", "three", "elf")
        self.assertTrue(registry.contains("test", 3, 2))
        self.assertFalse(registry.contains("test", 4, 2))


if __name__ == "__main__":
    unittest.main()
