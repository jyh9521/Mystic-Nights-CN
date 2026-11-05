"""Source-bound MIPS lookahead extension using the locale's encoded punctuation.

No code cave, heap change or game execution: the existing lookahead block is
replaced in-place. A read-only code table occupies verified NUL padding after
one translated C string, within that string's existing fixed capacity.
"""
import hashlib
import struct
from .font import encode_text


def sha(data):return hashlib.sha256(data).hexdigest()


def file_address(elf, offset, size=1):
    if elf[:7] != b"\x7fELF\x01\x01\x01":raise ValueError("Expected ELF32 little endian")
    phoff=struct.unpack_from("<I",elf,28)[0];stride,count=struct.unpack_from("<HH",elf,42)
    for i in range(count):
        kind,start,va,_,length,*_=struct.unpack_from("<8I",elf,phoff+i*stride)
        if kind==1 and start<=offset and offset+size<=start+length:return va+offset-start
    raise ValueError("Layout patch is outside a file-backed load segment")


def assemble_lookahead(start, stop, table_address, capacity):
    """Only standard scalar MIPS instructions; preserve v0 and all saved state."""
    code=[];labels={};fixups=[]
    def emit(word):code.append(word)
    def label(name):labels[name]=len(code)
    def imm(op,rt,rs,value):emit(op<<26|rs<<21|rt<<16|(value&65535))
    def branch(op,rs,rt,name):fixups.append((len(code),name));emit(op<<26|rs<<21|rt<<16)
    def jump(address):emit(2<<26|((address>>2)&0x3ffffff))
    # v1=s3+s2; next byte. Original uses s0=1 to allow a break.
    emit(19<<21|18<<16|3<<11|0x21);imm(0x24,4,3,0);imm(0x0c,5,4,0x80)
    branch(4,5,0,"ascii");imm(9,16,0,1)
    imm(0x24,5,3,1);emit(4<<16|4<<11|8<<6);emit(4<<21|5<<16|4<<11|0x25)
    branch(4,0,0,"table");emit(0)
    label("ascii")
    imm(0x0d,5,4,0x20);imm(9,5,5,-97);imm(0x0b,5,5,26)
    branch(5,5,0,"keep");emit(0)
    imm(9,5,4,-48);imm(0x0b,5,5,10);branch(5,5,0,"keep");emit(0)
    label("table");imm(0x0f,5,0,table_address>>16);imm(0x0d,5,5,table_address&65535)
    label("loop");imm(0x25,6,5,0);branch(4,6,0,"normal");imm(9,5,5,2)
    branch(5,6,4,"loop");emit(0)
    label("keep");jump(stop);emit(16<<11|0x25) # or s0,zero,zero (delay slot)
    label("normal");jump(stop);emit(0)
    for index,name in fixups:
        delta=labels[name]-index-1
        if not -32768<=delta<=32767:raise ValueError("Layout branch out of range")
        code[index]|=delta&65535
    payload=struct.pack('<'+'I'*len(code),*code)
    if len(payload)>capacity or capacity%4:raise ValueError("Layout block exceeds verified instruction span")
    if ((start+4)^stop)&0xf0000000:raise ValueError("Layout jump crosses address region")
    return payload+b'\0'*(capacity-len(payload))


def build_text_layout(original, current, entries, mapping, recipe, policy):
    if recipe.get('format')!='mips-text-lookahead' or recipe.get('version')!=1 or sha(original)!=recipe['source_sha256']:
        raise ValueError('Text layout source identity mismatch')
    if len(original)!=len(current):raise ValueError('Text layout input length changed')
    offset=recipe['offset'];expected=bytes.fromhex(recipe['expected_hex'])
    if original[offset:offset+len(expected)]!=expected or current[offset:offset+len(expected)]!=expected:
        raise ValueError('Text layout instruction anchor mismatch')
    start=file_address(original,offset,len(expected));stop=start+len(expected)
    owners=[r for r in entries if r['id']==recipe['padding_owner_id']]
    if len(owners)!=1:raise ValueError('Text layout padding owner missing/duplicate')
    row=owners[0]
    if (row['kind']!='elf' or row['resource']!=recipe['resource'] or row['source_sha256']!=recipe['padding_source_sha256']
            or row['offset']!=recipe['padding_offset'] or row['capacity']!=recipe['padding_capacity']):
        raise ValueError('Text layout padding owner changed')
    encoded=encode_text(row['target'],mapping)+b'\0';first=(row['offset']+len(encoded)+1)&~1
    end=row['offset']+row['capacity']
    if current[row['offset']:end]!=encoded.ljust(row['capacity'],b'\0'):
        raise ValueError('Text layout padding is not the verified translated C string')
    chars=policy['no_line_start']
    if not isinstance(chars,str) or not chars or len(set(chars))!=len(chars):raise ValueError('Invalid line-start punctuation policy')
    codes=sorted({ord(c) if ord(c)<128 else mapping[c] for c in chars if ord(c)<128 or c in mapping})
    table=struct.pack('<'+'H'*(len(codes)+1),*codes,0)
    if first+len(table)>end:raise ValueError('Translated string leaves insufficient punctuation-table padding')
    address=file_address(original,first,len(table))
    code=assemble_lookahead(start,stop,address,len(expected));output=bytearray(current)
    output[offset:offset+len(code)]=code;output[first:first+len(table)]=table
    report={'format':recipe['format'],'version':1,'resource':recipe['resource'],
            'recipe':recipe,'policy':policy,'code_start':start,'code_stop':stop,'table_address':address,
            'table_codes':codes,'padding_owner_id':row['id'],
            'writes':[{'offset':offset,'before':expected.hex(),'after':code.hex()},
                      {'offset':first,'before':bytes(len(table)).hex(),'after':table.hex()}]}
    return bytes(output),report


def replay_lookahead(code, start, stop, table_address, table_codes, next_bytes):
    """Bounded instruction-level fixture replay, not an emulator/game launch."""
    regs=[0]*32;regs[19]=0x10000;regs[2]=0x76543210;pc=start;pending=None
    table=struct.pack('<'+'H'*(len(table_codes)+1),*table_codes,0)
    memory={0x10000+i:v for i,v in enumerate(next_bytes+b'\0\0')}
    memory.update({table_address+i:v for i,v in enumerate(table)})
    for _ in range(2048):
        if pc==stop:
            if regs[2]!=0x76543210:raise AssertionError('Glyph pointer clobbered')
            return regs[16]==0
        if not start<=pc<start+len(code) or pc%4:raise ValueError('Fixture PC escaped block')
        word=struct.unpack_from('<I',code,pc-start)[0];op=word>>26;rs=word>>21&31;rt=word>>16&31;rd=word>>11&31
        u=word&65535;s=u if u<32768 else u-65536;target=None
        if word==0:pass
        elif op==0:
            fn=word&63
            if fn==0:regs[rd]=(regs[rt]<<(word>>6&31))&0xffffffff
            elif fn==0x21:regs[rd]=(regs[rs]+regs[rt])&0xffffffff
            elif fn==0x25:regs[rd]=regs[rs]|regs[rt]
            else:raise ValueError('Unsupported fixture R instruction')
        elif op==9:regs[rt]=(regs[rs]+s)&0xffffffff
        elif op==0x0b:regs[rt]=int(regs[rs]<(s&0xffffffff))
        elif op==0x0c:regs[rt]=regs[rs]&u
        elif op==0x0d:regs[rt]=regs[rs]|u
        elif op==0x0f:regs[rt]=u<<16
        elif op in (0x24,0x25):
            a=(regs[rs]+s)&0xffffffff;regs[rt]=memory[a]
            if op==0x25:regs[rt]|=memory[a+1]<<8
        elif op in (4,5):
            if (regs[rs]==regs[rt])==(op==4):target=pc+4+s*4
        elif op==2:target=((pc+4)&0xf0000000)|((word&0x3ffffff)<<2)
        else:raise ValueError('Unsupported fixture opcode')
        regs[0]=0;old_pending=pending;pending=target;pc=old_pending if old_pending is not None else pc+4
    raise ValueError('Fixture instruction budget exceeded')
