"""Replay the emitted scalar MIPS lookahead with synthetic text and a codebook."""
import unittest
import copy
import hashlib
import struct
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from mysticnights.text_layout import assemble_lookahead,replay_lookahead,build_text_layout
from mysticnights.font import downsample_coverage
from PIL import Image,ImageDraw


class LookaheadTests(unittest.TestCase):
    def fixture(self):
        data=bytearray(1024);data[:7]=b'\x7fELF\x01\x01\x01'
        struct.pack_into('<I',data,28,52);struct.pack_into('<HH',data,42,32,1)
        struct.pack_into('<8I',data,52,1,128,0x100000,0,896,896,7,128)
        data[512:520]=b'original';original=bytes(data)
        row={'id':'SAMPLE@200','kind':'elf','resource':'SAMPLE','offset':512,'capacity':154,
             'source_sha256':hashlib.sha256(b'original').hexdigest(),'target':'字'}
        recipe={'format':'mips-text-lookahead','version':1,'source_sha256':hashlib.sha256(original).hexdigest(),
                'resource':'SAMPLE','offset':128,'expected_hex':bytes(144).hex(),
                'padding_owner_id':row['id'],'padding_offset':512,'padding_capacity':154,
                'padding_source_sha256':row['source_sha256']}
        data[512:666]=b'\xa4\xa2'+bytes(152)
        return original,bytes(data),[row],{'。':0xa4a1,'字':0xa4a2},recipe,{'no_line_start':'。!'}

    def test_source_bound_table_is_after_c_string_nul_and_writes_rollback(self):
        args=self.fixture();before=args[1];after,report=build_text_layout(*args)
        self.assertEqual(after[512:515],b'\xa4\xa2\0')
        self.assertEqual(report['table_codes'],[33,0xa4a1])
        restored=bytearray(after)
        for w in report['writes']:
            offset=w['offset'];expected=bytes.fromhex(w['after']);old=bytes.fromhex(w['before'])
            self.assertEqual(after[offset:offset+len(expected)],expected)
            restored[offset:offset+len(old)]=old
        self.assertEqual(bytes(restored),before)

    def test_source_instruction_padding_owner_and_capacity_guards(self):
        original,current,rows,mapping,recipe,policy=self.fixture()
        bad=bytearray(original);bad[-1]=1
        with self.assertRaisesRegex(ValueError,'identity'):build_text_layout(bytes(bad),current,rows,mapping,recipe,policy)
        bad=bytearray(current);bad[128]=1
        with self.assertRaisesRegex(ValueError,'anchor'):build_text_layout(original,bytes(bad),rows,mapping,recipe,policy)
        bad=bytearray(current);bad[520]=1
        with self.assertRaisesRegex(ValueError,'padding'):build_text_layout(original,bytes(bad),rows,mapping,recipe,policy)
        bad=copy.deepcopy(recipe);bad['padding_owner_id']='missing'
        with self.assertRaisesRegex(ValueError,'owner'):build_text_layout(original,current,rows,mapping,bad,policy)
        with self.assertRaisesRegex(ValueError,'policy'):build_text_layout(original,current,rows,mapping,recipe,{'no_line_start':'。。'})

    def test_every_configured_code_and_ascii_word(self):
        start,stop,table=0x155eb0,0x155f40,0x252280
        keys=[ord(c) for c in '.,!?:;)]}%']+[0xa4a2,0xa4fe,0xb0a1]
        code=assemble_lookahead(start,stop,table,144)
        for key in keys:
            value=bytes([key]) if key<128 else key.to_bytes(2,'big')
            self.assertTrue(replay_lookahead(code,start,stop,table,keys,value),hex(key))
        for c in b'AZaz019':self.assertTrue(replay_lookahead(code,start,stop,table,keys,bytes([c])))
        for c in [b' ',b'\0',b'<',b'\xa4\xa3',b'\xb0\xa2']:
            self.assertFalse(replay_lookahead(code,start,stop,table,keys,c),repr(c))

    def test_all_bmp_two_byte_codes_no_false_positives(self):
        start,stop,table=0x155eb0,0x155f40,0x252280;keys=[0xa4a2,0xa4fe,0xb0a1]
        code=assemble_lookahead(start,stop,table,144)
        for hi in range(0x80,0x100):
            for lo in (0,0x20,0x7f,0x80,0xa1,0xa2,0xfe,0xff):
                self.assertEqual(replay_lookahead(code,start,stop,table,keys,bytes([hi,lo])),hi*256+lo in keys)

    def test_capacity_and_pc_validation(self):
        with self.assertRaises(ValueError):assemble_lookahead(0x1000,0x1100,0x2000,16)
        with self.assertRaises(ValueError):assemble_lookahead(0x1000,0x10001100,0x2000,144)

    def test_positive_filter_has_no_sidelobes_and_clean_edge_floor(self):
        large=Image.new('L',(52,52));ImageDraw.Draw(large).rectangle((16,8,23,43),fill=255)
        im=downsample_coverage(large,(13,13),{'filter':'box','edge_floor':24,'edge_ceiling':224})
        self.assertEqual(set(im.get_flattened_data()),{0,255})
        for y in range(13):self.assertEqual(im.getpixel((3,y)),0);self.assertEqual(im.getpixel((6,y)),0)
        with self.assertRaises(ValueError):downsample_coverage(large,(13,13),{'filter':'box','edge_floor':255,'edge_ceiling':24})


if __name__=='__main__':unittest.main()
