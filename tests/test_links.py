"""Synthetic link discovery; no game files or third-party reference needed."""
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from inspect_links import CAPACITY_SCOPE, inspect, link_item_names, pair_document_blocks, scan_scene_keys, write_reports


def scene_field(name=b"POTION", model=b"I001.GEO", tail=b""):
    return b"h\0" + (name+b"\0"+tail).ljust(32,b"\0") + (model+b"\0").ljust(32,b"\xcc")


def resource(members):
    result = bytearray(b"1.30\0\0\0\0Buil")
    for group in range(8):
        group_members = members.get(group, [])
        result += struct.pack("<I", len(group_members))
        for name, payload in group_members:
            result += name.encode().ljust(32,b"\0") + struct.pack("<I",len(payload)) + payload
    return bytes(result)


class FakeImage:
    def __init__(self, files):
        self.files = files
    def read(self, name):
        return self.files[name]


class LinkTests(unittest.TestCase):
    def test_complete_scene_fields_not_substrings(self):
        data = b"prefix" + scene_field(b"SUPER POTION", tail=b"\x80\xff")
        rows = scan_scene_keys(data)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["source_ko"],"SUPER POTION")
        self.assertEqual(rows[0]["capacity"],12)
        self.assertEqual(rows[0]["field_bytes"],32)
        self.assertEqual(rows[0]["member_relative_offset"],8)
        self.assertEqual(scan_scene_keys(data[:-1]),[])
        self.assertEqual(scan_scene_keys(b"i\0"+data[8:]),[])

    def test_scene_malformed_names_and_models(self):
        for data in (scene_field(model=b"not a file.GEO"), scene_field(name=b""),
                     scene_field(name=b"\xff"), scene_field(name=b"bad\nname"),
                     b"h\0"+b"A"*32+(b"I.GEO\0").ljust(32,b"\0")):
            with self.subTest(data=data):
                self.assertEqual(scan_scene_keys(data),[])

    def test_document_block_pairing_ignores_page_and_block_order(self):
        original = b'SCR_TYPE DOC\nITEM {\nNAME "A"\nTEXT 1 50 120 540 "one"\n}\nITEM {\nNAME "B"\nTEXT 1 50 120 540 "two"\n}\n'
        english = b'SCR_TYPE DOC\nITEM {\nNAME "Bee"\nTEXT 1 50 120 540 "B page"\n}\nITEM {\nNAME "Aye"\nTEXT 1 50 120 540 "A page 1"\nTEXT 2 50 120 540 "A page 2"\n}\n'
        report = pair_document_blocks(original,english,{"A":"Aye", "B":"Bee"})
        blocks = list(report["blocks"].values())
        self.assertEqual([r["source_name"] for r in blocks],["A","B"])
        self.assertEqual([f["source_ko"] for f in blocks[0]["en"]],["Aye","A page 1","A page 2"])
        self.assertEqual(blocks[0]["en"][-1]["page_number"],2)
        self.assertEqual(report["unmatched_en_blocks"],{})

    def test_missing_english_and_unmatched_blocks_are_explicit(self):
        original = b'SCR_TYPE DOC\nITEM {\nNAME "A"\nTEXT 1 1 1 1 "one"\n}\n'
        without = pair_document_blocks(original,None,{"A":None})
        self.assertEqual(next(iter(without["blocks"].values()))["en"],[])
        with_unknown = pair_document_blocks(original,original,{"A":"different"})
        self.assertEqual(len(with_unknown["unmatched_en_blocks"]),1)
        self.assertEqual(next(iter(with_unknown["blocks"].values()))["en"],[])

    def test_duplicate_document_name_fails(self):
        original = b'SCR_TYPE DOC\nITEM {\nNAME "A"\n}\n'
        english = original + b'ITEM {\nNAME "A"\n}\n'
        with self.assertRaises(ValueError):
            pair_document_blocks(original,english,{"A":"A"})

    def test_inventory_optional_reference_and_capacity_scope(self):
        item = b'SCR_TYPE ITEM\nITEM {\nID 1\nNAME "POTION"\nDESCRIPTION "HP"\n}\n'
        image = FakeImage({"RES/SUBSYS.RES":resource({5:[("ITEM.SCR",item)]}),
                           "RES/SCENE/A.RES":resource({7:[("A.SCN",scene_field())]})})
        reports = inspect(image)
        summary = reports["summary.json"]
        self.assertEqual(summary["canonical_item_names"],1)
        self.assertEqual(summary["mapped_scene_keys"],1)
        self.assertEqual(summary["upstream_res_files"],0)
        self.assertIsNone(reports["item_names.json"][0]["reference_en"])
        self.assertEqual(reports["item_names.json"][0]["minimum_capacity"],6)
        self.assertEqual(reports["item_names.json"][0]["capacity_scope"],CAPACITY_SCOPE)
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual(inspect(image,Path(temporary))["summary.json"]["upstream_res_files"],0)
            path=Path(temporary)/"RES";path.mkdir()
            (path/"SUBSYS.RES").write_bytes(resource({5:[("ITEM.SCR",item.replace(b'"POTION"',b'"REMEDY"'))]}))
            reference=inspect(image,Path(temporary))
            self.assertEqual(reference["item_names.json"][0]["reference_en"],"REMEDY")
            self.assertEqual(reference["summary.json"]["upstream_res_files"],1)

    def test_unmapped_scene_key_not_attached_to_substring(self):
        item = b'SCR_TYPE ITEM\nITEM {\nID 1\nNAME "POTION"\n}\n'
        reports=inspect(FakeImage({"RES/SUBSYS.RES":resource({5:[("ITEM.SCR",item)]}),
                                  "RES/A.RES":resource({7:[("A.SCN",scene_field(b"SUPER POTION"))]})}))
        self.assertEqual(reports["summary.json"]["unmapped_scene_keys"],1)
        self.assertEqual(len(reports["item_names.json"][0]["references"]),1)

    def test_duplicate_canonical_name_fails(self):
        item=b'SCR_TYPE ITEM\nITEM {\nID 1\nNAME "A"\n}\nITEM {\nID 2\nNAME "A"\n}\n'
        with self.assertRaises(ValueError):
            inspect(FakeImage({"RES/SUBSYS.RES":resource({5:[("ITEM.SCR",item)]})}))

    def test_report_output_exclusive_and_readable(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/"reports"
            reports={"summary.json":{"test":"中文"}}
            write_reports(reports,path)
            self.assertEqual(json.loads((path/"summary.json").read_text(encoding="utf-8")),reports["summary.json"])
            with self.assertRaises(FileExistsError):
                write_reports(reports,path)
            with self.assertRaises(ValueError):
                write_reports({"../escape.json":{}},Path(temporary)/"other")


if __name__=="__main__":
    unittest.main()
