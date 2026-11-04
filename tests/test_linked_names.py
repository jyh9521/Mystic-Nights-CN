"""Synthetic atomic-name and bounded ELF tests; no game/runtime dependencies."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))
from inspect_links import inspect
from mysticnights.linked_names import (
    MAIN_ELF, NameLinkError, audit_elf_suffix_references, discover_name_links, elf_load_segments, find_elf_names, patch_linked_names,
)
from mysticnights.resources import parse_res


def make_res(members):
    result = bytearray(b"1.30\0\0\0\0Buil")
    for group in range(8):
        entries = members.get(group, [])
        result += struct.pack("<I",len(entries))
        for name, payload in entries:
            result += name.encode().ljust(32,b"\0") + struct.pack("<I",len(payload)) + payload
    return bytes(result)


def make_elf(payload=b"\0POTION\0BLADE\0SUPER BLADE\0PREFIXPOTION\0"):
    result = bytearray(0x200)
    result[:16] = b"\x7fELF\x01\x01\x01".ljust(16,b"\0")
    struct.pack_into("<HHIIIIIHHHHHH",result,16,2,8,1,0x100000,52,0,0,52,32,1,40,0,0)
    struct.pack_into("<8I",result,52,1,0x80,0x100000,0x100000,0x80,0x80,7,128)
    result[0x80:0x80+len(payload)] = payload
    # A debug-like literal outside all PT_LOAD ranges must never be selected.
    result[0x180:0x18E] = b"\0POTION\0BLADE\0"
    return bytes(result)


def scene(name=b"POTION"):
    return b"h\0" + (name+b"\0\xbb\xcc").ljust(32,b"\0") + b"I001.GEO\0".ljust(32,b"\xcc")


class Image:
    def __init__(self, files):
        self.files = dict(files)
    def read(self, name):
        return self.files[name]


def fixture():
    items = b'SCR_TYPE ITEM\nITEM {\nID 1\nNAME "POTION"\nDESCRIPTION "POTION heals"\n}\nITEM {\nID 2\nNAME "BLADE"\n}\nITEM {\nID 3\nNAME "SUPER BLADE"\n}\n'
    event = b'SCR_TYPE EVENT\nEVENT {\nEVENT_ID 1\nITEM_LIST "POTION"\nSHOW "POTION"\nTEXT "POTION" 60\n}\n'
    net = b'SCR_TYPE ITEM\nITEM {\nID 1\nNAME "POTION"\n}\n'
    drop = b'SCR_TYPE VAMPIRE\nVAMPIRE {\nTYPE 1\nITEM 10 "POTION"\n}\n'
    doc = b'SCR_TYPE DOC\nITEM {\nNAME "POTION"\nTEXT 1 1 1 1 "story"\n}\n'
    return Image({MAIN_ELF:make_elf(),
                  'RES/SUBSYS.RES':make_res({5:[('ITEM.SCR',items),('EVENT.SCR',event)]}),
                  'RES/NETSUB.RES':make_res({5:[('ITEM.SCR',net),('VAMPIRE.SCR',drop)]}),
                  'RES/UI/DOCUMENT.RES':make_res({5:[('DOCUMENT.SCR',doc)]}),
                  'RES/UI/ITEM.RES':make_res({5:[('DOCUMENT.SCR',doc)]}),
                  'RES/SCENE/A.RES':make_res({7:[('A.SCN',scene())]})})


class LinkedNameTests(unittest.TestCase):
    def test_load_segment_and_nul_boundary_excludes_suffix_and_debug(self):
        elf = make_elf()
        rows, rejected, loads = find_elf_names(elf, {'id:1':'POTION','id:2':'BLADE','id:3':'SUPER BLADE'})
        self.assertEqual(len(loads),1)
        self.assertEqual([row['source'] for row in rows],['POTION','BLADE','SUPER BLADE'])
        self.assertEqual(len(rejected),2)
        self.assertTrue(all(0x80 <= row['offset'] < 0x100 for row in rows))
        self.assertEqual(rows[0]['context']['virtual_address'],0x100001)
        self.assertEqual(rows[0]['capacity'],7)
        self.assertEqual(rows[0]['max_encoded_bytes'],6)

    def test_load_segment_start_counts_as_boundary(self):
        rows, _, _ = find_elf_names(make_elf(b'POTION\0'),{'id:1':'POTION'})
        self.assertEqual(rows[0]['offset'],0x80)

    def test_suffix_audit_distinguishes_literals_and_immediate_candidates(self):
        names={'id:1':'POTION','id:2':'BLADE','id:3':'SUPER BLADE'}
        original=make_elf();fields,rejected,loads=find_elf_names(original,names)
        suffix=rejected[0];virtual=0x100000+suffix['offset']-0x80
        data=bytearray(original)
        struct.pack_into('<I',data,0xD0,virtual)
        struct.pack_into('<I',data,0xD9,virtual)
        struct.pack_into('<I',data,0xE0,(15<<26)|(4<<16)|((virtual+0x8000)>>16))
        struct.pack_into('<I',data,0xE4,(9<<26)|(4<<21)|(4<<16)|(virtual&0xFFFF))
        fields,rejected,_=find_elf_names(bytes(data),names)
        audit=audit_elf_suffix_references(bytes(data),rejected,fields)
        self.assertEqual(audit['summary']['aligned_u32_address_hits'],1)
        self.assertEqual(audit['summary']['unaligned_byte_hits'],1)
        selected=next(row for row in audit['suffixes'] if row['file_offset']==suffix['offset'])
        self.assertEqual(selected['exact_low_immediate_candidates'][0]['prior_32_word_matching_lui_candidates'],[0xE0])

    def test_suffix_audit_does_not_claim_no_computed_references(self):
        data=make_elf();fields,rejected,_=find_elf_names(data,{'id:1':'POTION','id:2':'BLADE','id:3':'SUPER BLADE'})
        audit=audit_elf_suffix_references(data,rejected,fields)
        self.assertIn('not proof',audit['conclusion'])
        self.assertEqual(audit['summary']['aligned_u32_address_hits'],0)
        bad=copy.deepcopy(rejected);bad[0]['offset']=0
        with self.assertRaises(NameLinkError):
            audit_elf_suffix_references(data,bad,fields)

    def test_elf_invalid_headers_and_ranges(self):
        examples = [b'',make_elf()[:70]]
        for offset, fmt, value in ((18,'<H',62),(20,'<I',2),(28,'<I',0x1F0),(42,'<H',31),(44,'<H',0),
                                   (52+16,'<I',0x300),(52+20,'<I',1),(52+28,'<I',3)):
            bad = bytearray(make_elf());struct.pack_into(fmt,bad,offset,value);examples.append(bytes(bad))
        for bad in examples:
            with self.subTest(length=len(bad)),self.assertRaises(NameLinkError):
                elf_load_segments(bad)

    def test_manifest_is_deterministic_and_cross_checks_existing_report(self):
        image = fixture()
        first = discover_name_links(image,inspect_report=inspect(image))
        second = discover_name_links(image)
        self.assertEqual(first,second)
        self.assertEqual(first['summary']['canonical_names'],3)
        self.assertEqual(first['summary']['elf_exact_fields'],3)
        self.assertEqual(first['summary']['gaps'],0)
        self.assertEqual(first['network']['definitions'][0]['id'],'id:1')
        bad = inspect(image)
        bad['item_names.json'][0]['references'].pop()
        with self.assertRaises(NameLinkError):
            discover_name_links(image,inspect_report=bad)

    def test_atomic_replace_updates_all_kinds_and_no_other_bytes(self):
        image = fixture();before = dict(image.files)
        manifest = discover_name_links(image)
        encoded = b'\xa4\xa1\xa4\xa2'
        output = patch_linked_names(image,manifest,{'id:1':'药剂'},lambda _:encoded)
        self.assertEqual(image.files,before)
        group = next(row for row in manifest['groups'] if row['id']=='id:1')
        self.assertEqual({row['kind'] for row in group['references']},{'script','scn','elf'})
        self.assertEqual(set(output),{row['resource'] for row in group['references']})
        for resource,revised in output.items():
            expected = bytearray(before[resource])
            for row in group['references']:
                if row['resource']==resource:
                    value=encoded+(b'\0' if row['capacity_includes_nul'] else b'')
                    expected[row['offset']:row['offset']+row['capacity']]=value.ljust(row['capacity'],b'\0')
            self.assertEqual(revised,bytes(expected))
        event=parse_res(output['RES/SUBSYS.RES']).read('EVENT.SCR')
        self.assertIn(b'SHOW "POTION"',event)
        self.assertIn(b'TEXT "POTION"',event)
        self.assertEqual(output[MAIN_ELF][0x180:0x18E],before[MAIN_ELF][0x180:0x18E])
        scn=parse_res(output['RES/SCENE/A.RES']).read('A.SCN')
        self.assertEqual(scn[9:34],scene()[9:34])

    def test_basic_weapon_not_replaced_inside_longer_weapon(self):
        image=fixture();manifest=discover_name_links(image)
        output=patch_linked_names(image,manifest,{'id:2':'刀'},lambda _:b'XX')
        self.assertIn(b'\0SUPER BLADE\0',output[MAIN_ELF])
        self.assertIn(b'NAME "SUPER BLADE"',output['RES/SUBSYS.RES'])

    def test_source_preserving_noop_returns_no_payloads(self):
        image=fixture();manifest=discover_name_links(image)
        self.assertEqual(patch_linked_names(image,manifest,{},lambda _:b'bad'),{})
        self.assertEqual(patch_linked_names(image,manifest,{'id:1':'POTION'},lambda _:b'bad'),{})

    def test_overflow_and_invalid_encoder_abort_without_input_changes(self):
        image=fixture();before=dict(image.files);manifest=discover_name_links(image)
        encoders=(lambda _:b'A'*7,lambda _:b'',lambda _:b'bad\0',lambda _:'not bytes',lambda _:b'"')
        for encode in encoders:
            with self.subTest(encode=encode),self.assertRaises(NameLinkError):
                patch_linked_names(image,manifest,{'id:1':'new'},encode)
            self.assertEqual(image.files,before)

    def test_exact_capacity_is_accepted(self):
        image=fixture();manifest=discover_name_links(image)
        output=patch_linked_names(image,manifest,{'id:1':'changed'},lambda _:b'REMEDY')
        self.assertIn(b'\0REMEDY\0',output[MAIN_ELF])

    def test_invalid_target_unknown_id_and_collisions(self):
        image=fixture();manifest=discover_name_links(image)
        for targets in ({'id:99':'test'},{'id:1':''},{'id:1':' '},{'id:1':'bad"'},
                        {'id:1':'%s'},{'id:1':123},{'id:1':'BLADE'},
                        {'id:1':'NEW','id:2':'NEW'}):
            with self.subTest(targets=targets),self.assertRaises(NameLinkError):
                patch_linked_names(image,manifest,targets,lambda text:text.encode('ascii'))
        with self.assertRaises(NameLinkError):
            patch_linked_names(image,manifest,{'id:1':'alpha','id:2':'beta'},lambda _:b'SAME')

    def test_manifest_deleted_reference_rejected_even_with_recomputed_digest(self):
        image=fixture();manifest=discover_name_links(image)
        broken=copy.deepcopy(manifest);broken['groups'][0]['references'].pop()
        core={key:broken[key] for key in ('format','version','scope','network','gaps','elf_rejected_suffixes')}
        core['groups']=[{k:v for k,v in row.items() if k!='reference_en'} for row in broken['groups']]
        broken['core_sha256']=hashlib.sha256(json.dumps(core,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        with self.assertRaises(NameLinkError):
            patch_linked_names(image,broken,{'id:1':'new'},lambda _:b'NEW')

    def test_source_or_scope_changes_invalidate_manifest(self):
        image=fixture();manifest=discover_name_links(image)
        image.files[MAIN_ELF]=image.files[MAIN_ELF][:-1]+b'!'
        with self.assertRaises(NameLinkError):
            patch_linked_names(image,manifest,{'id:1':'new'},lambda _:b'NEW')
        image=fixture();image.files['RES/ADDED.RES']=make_res({})
        with self.assertRaises(NameLinkError):
            patch_linked_names(image,manifest,{'id:1':'new'},lambda _:b'NEW')

    def test_network_extra_and_unresolved_drop_are_reported_and_blocked(self):
        image=fixture()
        net=b'SCR_TYPE ITEM\nITEM {\nID 9\nNAME "OTHER"\n}\n'
        drop=b'SCR_TYPE VAMPIRE\nVAMPIRE {\nTYPE 1\nITEM 10 "LOST"\n}\n'
        image.files['RES/NETSUB.RES']=make_res({5:[('ITEM.SCR',net),('VAMPIRE.SCR',drop)]})
        manifest=discover_name_links(image)
        self.assertEqual(manifest['summary']['network_extra_names'],1)
        self.assertTrue(manifest['network']['drops_without_local_definition'])
        with self.assertRaises(NameLinkError):
            patch_linked_names(image,manifest,{'id:1':'new'},lambda _:b'NEW')

    def test_network_id_disagreement_is_not_silently_merged(self):
        image=fixture()
        net=b'SCR_TYPE ITEM\nITEM {\nID 99\nNAME "POTION"\n}\n'
        image.files['RES/NETSUB.RES']=make_res({5:[('ITEM.SCR',net)]})
        manifest=discover_name_links(image)
        self.assertEqual(len(manifest['network']['id_mismatches']),1)
        with self.assertRaises(NameLinkError):
            patch_linked_names(image,manifest,{'id:1':'new'},lambda _:b'NEW')

    def test_change_between_discovery_and_copy_is_detected(self):
        base=fixture();manifest=discover_name_links(base)
        class ChangingImage(Image):
            def __init__(self,files):
                super().__init__(files);self.counts={}
            def read(self,name):
                self.counts[name]=self.counts.get(name,0)+1
                data=super().read(name)
                if name=='RES/SUBSYS.RES' and self.counts[name]>1:
                    return data[:-1]+bytes([data[-1]^1])
                return data
        with self.assertRaises(NameLinkError):
            patch_linked_names(ChangingImage(base.files),manifest,{'id:1':'new'},lambda _:b'NEW')


if __name__=='__main__':
    unittest.main()
