import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mysticnights.auxiliary import patch_auxiliary_slots, merge_resource_edits, extra_elf_entries, nul_candidates, extract_auxiliary, read_auxiliary
from mysticnights.scripts import validate_script_tokens, ScriptError
from mysticnights.catalogues import validate_literal_fields


class AuxiliaryTests(unittest.TestCase):
    def row(self, source="Original", target="Target"):
        raw=source.encode("utf8")
        return {"id":"SAMPLE@00000002", "offset":2, "source":source,"target":target,
                "encoding":"utf-8","source_bytes":len(raw),"source_sha256":hashlib.sha256(raw).hexdigest()}

    def test_slot_round_trip_and_isolation(self):
        data=b"xxOriginal\0yy"
        self.assertEqual(patch_auxiliary_slots(data,[self.row(target="Original")],str.encode),data)
        self.assertEqual(patch_auxiliary_slots(data,[self.row()],str.encode),b"xxTarget\0\0\0yy")
        self.assertEqual(data,b"xxOriginal\0yy")

    def test_unknown_source_hash_nul_overflow_and_overlap_rejected(self):
        row=self.row(); data=b"xxOriginal\0yy"
        for change in ({"source_sha256":"0"*64}, {"offset":1}, {"target":"T"*10}, {"target":"A\0B"}):
            with self.assertRaises(ValueError):patch_auxiliary_slots(data,[{**row,**change}],str.encode)
        with self.assertRaises(ValueError):patch_auxiliary_slots(data,[row,row],str.encode)

    def test_plain_file_terminal_and_padding(self):
        row=self.row(source="Some prose<END>",target="Text<END>")
        data=b"xxSome prose<END>"
        result=patch_auxiliary_slots(data,[row],str.encode,plain=True)
        self.assertEqual(result,b"xxText<END>"+b"\0"*6)
        self.assertEqual(len(result),len(data))

    def test_merge_disjoint_identical_and_conflict(self):
        self.assertEqual(merge_resource_edits(b"abc",b"Xbc",b"abY"),b"XbY")
        self.assertEqual(merge_resource_edits(b"abc",b"Xbc",b"XbY"),b"XbY")
        with self.assertRaises(ValueError):merge_resource_edits(b"abc",b"Xbc",b"Ybc")
        with self.assertRaises(ValueError):merge_resource_edits(b"abc",b"abc!",b"abc")

    def test_nul_candidates_require_printable_source(self):
        data=b"\x01broken\0"+"확인".encode("utf8")+b"\0English\0"
        rows=list(nul_candidates(data,"utf-8",[(0xAC00,0xD7A3)]))
        self.assertEqual([(x[0],x[2]) for x in rows],[(8,"확인")])


class DiscoveryTests(unittest.TestCase):
    def test_encoding_filter_and_terminated_fields_only(self):
        data = b"English\0" + "확인".encode("utf8") + b"\0\xff\0tail"
        self.assertEqual(list(nul_candidates(data, "utf-8", [(0xAC00, 0xD7A3)])),
                         [(8, "확인".encode("utf8"), "확인")])

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


class CataloguePaddingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.resources = {"NETGUICD.ELF": b"Network message\0",
                          "DATA/AGREE.TXT": b"Original prose<END>\r\r\n",
                          "SCKA_200.55": b"Lv. MAX\0" + b"\0" * 8 + b"TAIL"}
        resources = self.resources
        class Image:
            def read(self, name): return resources[name]
        self.image = Image()
        self.config = {"locale": "xx", "network": "network.json", "agreement": "agreement.json",
                       "extra_interface": "extra.json", "punctuation": {}}
        self.recipe = {"sources": [
            {"resource": "NETGUICD.ELF", "encoding": "utf-8", "layout": "nul-candidates"},
            {"resource": "DATA/AGREE.TXT", "encoding": "cp949", "layout": "plain"},
            {"resource": "SCKA_200.55", "encoding": "cp949", "layout": "explicit-slots",
             "slots": [{"offset": 0, "source": "Lv. MAX"}]}]}

    def write_catalogues(self):
        for key, group in zip(("network", "agreement", "extra_interface"),
                              extract_auxiliary(self.image, self.recipe)):
            for row in group["entries"]:
                row.update(target=row["source"], status="draft", role="display", patch_ready=True)
            (self.root / self.config[key]).write_text(json.dumps({"locale": "xx", "entries": group["entries"]}),
                                                     encoding="utf8")

    def change_extra(self, **values):
        path = self.root / self.config["extra_interface"]
        data = json.loads(path.read_text(encoding="utf8"))
        data["entries"][0].update(values)
        path.write_text(json.dumps(data), encoding="utf8")

    def read(self, with_image):
        return read_auxiliary(self.root, self.config, self.recipe, self.image if with_image else None)

    def test_default_and_explicit_zero_padding_are_equivalent(self):
        self.write_catalogues()
        for with_image in (True, False):
            with self.subTest(with_image=with_image):
                self.assertNotIn("padding_bytes", self.read(with_image)["extra_interface"][0])
        self.change_extra(padding_bytes=0)
        for with_image in (True, False):
            self.assertEqual(self.read(with_image)["extra_interface"][0]["padding_bytes"], 0)

    def test_locale_cannot_authorize_undeclared_padding(self):
        self.write_catalogues()
        self.change_extra(padding_bytes=8, target="等级已达上限")
        for with_image in (True, False):
            with self.subTest(with_image=with_image), self.assertRaisesRegex(ValueError, "padding"):
                self.read(with_image)

    def test_reviewed_padding_is_accepted_and_patch_is_isolated(self):
        self.recipe["sources"][2]["slots"][0]["padding_bytes"] = 2
        self.write_catalogues()
        self.change_extra(target="New label")
        for with_image in (True, False):
            row = self.read(with_image)["extra_interface"][0]
            self.assertEqual(extra_elf_entries([row])[0]["capacity"], 10)
            original = self.resources["SCKA_200.55"]
            changed = patch_auxiliary_slots(original, [row], str.encode)
            self.assertEqual(changed, b"New label\0" + original[10:])

    def test_reviewed_padding_cannot_be_increased_decreased_or_removed(self):
        self.recipe["sources"][2]["slots"][0]["padding_bytes"] = 2
        self.write_catalogues()
        for value in (0, 1, 3, 8):
            self.change_extra(padding_bytes=value)
            for with_image in (True, False):
                with self.subTest(value=value, with_image=with_image), self.assertRaises(ValueError):
                    self.read(with_image)
        path = self.root / self.config["extra_interface"]
        data = json.loads(path.read_text(encoding="utf8"))
        del data["entries"][0]["padding_bytes"]
        path.write_text(json.dumps(data), encoding="utf8")
        for with_image in (True, False):
            with self.assertRaises(ValueError):
                self.read(with_image)

    def test_padding_requires_a_bounded_integer(self):
        self.write_catalogues()
        for value in (False, True, -1, 16, "0", None):
            self.change_extra(padding_bytes=value)
            for with_image in (True, False):
                with self.subTest(value=value, with_image=with_image), self.assertRaises(ValueError):
                    self.read(with_image)


class LiteralTextTests(unittest.TestCase):
    def test_exact_literal_exception_preserves_control_order(self):
        pair={"source":"<GATE OPEN>","target":"<门已开启>"}
        validate_script_tokens("<BR><GATE OPEN><O>","<BR><门已开启><O>",[pair])
        for target in ("<门已开启><BR><O>","<BR><门已开启><X>"):
            with self.assertRaises(ScriptError):validate_script_tokens("<BR><GATE OPEN><O>",target,[pair])
        with self.assertRaises(ScriptError):validate_script_tokens("<GATE OPEN>","<门已开启>")

    def test_real_controls_cannot_be_marked_literal(self):
        for source,target in (("<BR>","<换行>"),("<O>","<X>"),("<Heading>","<O>")):
            with self.assertRaises(ScriptError):validate_script_tokens(source,target,[{"source":source,"target":target}])

    def test_recipe_binds_id_and_original_hash(self):
        row={"id":"SAMPLE@1","source_sha256":"sourcehash","kind":"script","source":"<Heading>","target":"<标题>",
             "literal_token_translations":[{"source":"<Heading>","target":"<标题>"}]}
        recipe={"format":"literal-display-fields","version":1,"original_iso_sha256":"isohash",
                "entries":[{"id":"SAMPLE@1","source_sha256":"sourcehash","literal_tokens":["<Heading>"]}]}
        validate_literal_fields([row],recipe,"isohash")
        for change in ({"id":"SAMPLE@2"},{"source_sha256":"changed"}):
            with self.assertRaises(ValueError):validate_literal_fields([{**row,**change}],recipe,"isohash")
        with self.assertRaises(ValueError):validate_literal_fields([row],recipe,"different-iso")


if __name__=="__main__":unittest.main()
