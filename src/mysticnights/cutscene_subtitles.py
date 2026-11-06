"""Source-bound, frame-driven completion of the retail cutscene caption scaffold.

The retail loader already allocates/parses CAPTION nodes, but its type-2
dispatcher does nothing and its render loop never draws them. This module
adds a draw-before-Flip hook, not a host timer. It uses only verified zero
padding *after* translated ELF C-string terminators; embedded IOP modules,
ELF layout, heap, original node ordering and voice playback remain untouched.

All generated code is independently replayable. Static replay is not game
execution or evidence that a transcript has been heard/reviewed.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
import struct
from typing import Callable, Mapping, Sequence

from .font import encode_text
from .resources import parse_res
from .runtime_patches import address_offset


ORIGINAL_ELF_SHA256 = 'a8662cb99c7dd8abc66c6766d27e0fc15ff83fb3a04d2837001b87f88cf899c4'
ORIGINAL_ISO_SHA256 = '4eacce4ea467ade6ac04f7006c216d8ba6504661bc0e3d11ac990eed7e379c3b'
ELF_SIZE = 3428048
HOOK_ADDRESS = 0x159748
FLIP_ADDRESS = 0x127630
CUTSCENE_ADDRESS = 0x29FB30
FONT_ENV_ADDRESS = 0x2C4000
FONT_RESET_ADDRESS = 0x1558F0
FONT_COLOR_ADDRESS = 0x1559D0
RENDER_STRING_ADDRESS = 0x155C70
ALPHA_MODE_ADDRESS = 0x1273B0
CAPTION_DEFAULTS = ((0x13AAEC, 8, 40), (0x13AAF4, 7, 350))

# Small machine-code anchors, not redistributed complete game functions.
ANCHORS = {
    0x138CD8: '0000b07f000083840800612c',
    0x1391B4: '32fb43840400828410006214',
    0x139234: '32fb63842a00023ce0fd842401006324c8e2040c32fb43a4',
    0x13AB48: '020028a6040027a6',
    0x13AAEC: '8c0008243481858786010724',
    0x13AC60: '040003862d2060022d2840027000a62721106200ffff4224',
    0x13AC78: 'e84b050c0c0022a6',
    0x13BB84: '44ff63844010030021104300c0a80200',
    0x13C384: 'acea040c3c02a727',
    0x1F4B40: 'a0ed040c02000526',
    0x153118: '0d00062409000324200002243b000524',
    0x153220: '0000648e211850020d00022400008480000064a00000638e01006324',
    0x153250: '0000638e2500053c21105002d000a4276002a52401006324000063ae0000638e01006324000063ae',
    HOOK_ADDRESS: '8c9d040c00000000',
}

# POSITION has a keyword ID, but the SOUND reader explicitly skips its line.
# The allocation and playback anchors independently exclude a position vector
# from the eight-byte record. See docs/CUTSCENE_SUBTITLES.md, capacity section.
SOUND_POSITION_ANCHORS = {
    0x13C128: '2500043c510105249c4d050c08d88424',
    0x13C198: '2500043c510105249c4d050c08d88424',
    0x24D808: '504f534954494f4e00',
    0x13ADB0: '510103244400431000000000',
    0x13AEC8: '2d20a0022d2860023c4c050c2d30400202000324b4ff431400000000',
    0x13BB20: '3cff82a43cff6284c0a80200ea6f040c2d20a0022a00033c2d30a00240ff62ac2d2040004c73040c2d280000',
    0x138DF0: '020005240500c6807c0046a00200068640ff638cc03006002118c300040066801500c5102d204000010003240d00c310000000000300c0100000000071000010000000002a00023c2a00053c64fb4cc440fba524cc8a050c2d30a00069000010000000002a00023c0889050c90ff44ac64000010000000006889050c000000006000001000000000',
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inspect_engine(elf: bytes) -> dict:
    """Prove the unfinished retail scaffold from this exact supported ELF."""
    if len(elf) != ELF_SIZE or sha(elf) != ORIGINAL_ELF_SHA256:
        raise ValueError('Cutscene engine requires the supported original ELF')
    rows = []
    for address, expected_hex in ANCHORS.items():
        expected = bytes.fromhex(expected_hex)
        offset = address_offset(elf, address, len(expected))
        if elf[offset:offset + len(expected)] != expected:
            raise ValueError(f'Cutscene anchor mismatch: {address:#x}')
        rows.append({'address': address, 'offset': offset, 'expected_hex': expected_hex})
    table_offset = address_offset(elf, 0x24D3C0, 32)
    dispatch = list(struct.unpack_from('<8I', elf, table_offset))
    if dispatch[2] != 0x138FF4:
        raise ValueError('Retail CAPTION dispatch is not the verified no-op')
    return {
        'source_sha256': sha(elf), 'source_size': len(elf), 'anchors': rows,
        'caption_dispatch': dispatch[2], 'caption_dispatch_status': 'no-op',
        'caption_record_size': 24, 'node_record_size': 6,
        'cutscene_address': CUTSCENE_ADDRESS, 'font_environment_size': 32,
        'render_hook_address': HOOK_ADDRESS, 'flip_address': FLIP_ADDRESS,
        'frame_semantics': 'UpdateCutscene processes iFrame then increments it; draw uses iFrame-1',
        'script_semantics': 'GetToken reads exactly one CRLF command line; GetNextWord consumes its parameters',
        'evidence': 'supported original bytes and embedded DWARF1; no game execution',
    }


def inspect_sound_position_elision(elf: bytes) -> dict:
    """Guard the exact reader which ignores SOUND POSITION (not a zero default)."""
    if len(elf) != ELF_SIZE or sha(elf) != ORIGINAL_ELF_SHA256:
        raise ValueError('SOUND POSITION elision requires the supported original ELF')
    rows = []
    for address, expected_hex in SOUND_POSITION_ANCHORS.items():
        expected = bytes.fromhex(expected_hex)
        offset = address_offset(elf, address, len(expected))
        if elf[offset:offset + len(expected)] != expected:
            raise ValueError(f'SOUND POSITION anchor mismatch: {address:#x}')
        rows.append({'address': address, 'offset': offset, 'expected_hex': expected_hex})
    return {'source_sha256': sha(elf), 'source_size': len(elf), 'anchors': rows,
            'sound_record_size': 8,
            'semantics': 'POSITION keyword 0x151 branches directly to next GetToken; no position stores',
            'evidence': 'supported original bytes; static control-flow replay, not game execution'}


def _tokens(data: bytes) -> list[bytes]:
    """Retail SCR tokens; comments/whitespace only are discarded."""
    result = []
    p = 0
    while p < len(data):
        b = data[p]
        if b in b' \t\r\n':
            p += 1
        elif b == 59:  # semicolon comment, outside a quoted token
            while p < len(data) and data[p] not in (10, 13):
                p += 1
        elif b in (123, 125):
            result.append(data[p:p + 1]); p += 1
        elif b == 34:
            end = data.find(b'"', p + 1)
            if end < 0 or b'\0' in data[p:end] or b'\r' in data[p:end] or b'\n' in data[p:end]:
                raise ValueError('Malformed SCR quoted token')
            result.append(data[p:end + 1]); p = end + 1
        else:
            end = p
            while end < len(data) and data[end] not in b' \t\r\n{};"':
                end += 1
            if end == p or b'\0' in data[p:end]:
                raise ValueError('Malformed SCR token')
            result.append(data[p:end]); p = end
    return result


def _blocks(tokens: list[bytes]) -> list[tuple[bytes, list[bytes]]]:
    if tokens[:2] != [b'SCR_TYPE', b'CUTSCENE'] or tokens[-1:] != [b'END']:
        raise ValueError('Expected a complete CUTSCENE SCR')
    rows = []
    p = 2
    while p < len(tokens) - 1:
        name = tokens[p]
        if not re.fullmatch(rb'[A-Z_][A-Z_0-9]*', name) or tokens[p + 1:p + 2] != [b'{']:
            raise ValueError('Unsupported top-level cutscene statement')
        first = p + 2; depth = 1; p = first
        while p < len(tokens) and depth:
            depth += (tokens[p] == b'{') - (tokens[p] == b'}')
            p += 1
        if depth:
            raise ValueError('Unbalanced cutscene braces')
        rows.append((name, tokens[first:p - 1]))
    if p != len(tokens) - 1 or not rows or rows[0][0] != b'INIT_DATA':
        raise ValueError('Missing/duplicate cutscene INIT_DATA')
    if any(name == b'INIT_DATA' for name, _ in rows[1:]):
        raise ValueError('Duplicate INIT_DATA')
    return rows


def _line_blocks(data: bytes) -> list[tuple[bytes, list[list[bytes]]]]:
    """Retail GetToken consumes one CRLF line per command, not a token stream."""
    if b'\r' in data.replace(b'\r\n', b'') or b'\n' in data.replace(b'\r\n', b''):
        raise ValueError('Cutscene SCR requires the retail CRLF line framing')
    lines = [_tokens(line) for line in data.split(b'\r\n')]
    lines = [line for line in lines if line]
    if not lines or lines[0] != [b'SCR_TYPE', b'CUTSCENE'] or lines[-1] != [b'END']:
        raise ValueError('Expected native CUTSCENE header/END command lines')
    rows = []; index = 1
    while index < len(lines) - 1:
        header = lines[index]
        if len(header) != 2 or header[1] != b'{' or not re.fullmatch(rb'[A-Z_][A-Z_0-9]*', header[0]):
            raise ValueError('Unsupported native cutscene block header line')
        body = []; index += 1
        while index < len(lines) and lines[index] != [b'}']:
            line = lines[index]
            if any(token in (b'{', b'}') for token in line) or not re.fullmatch(rb'[A-Z_][A-Z_0-9]*', line[0]):
                raise ValueError('Unsupported native cutscene command line')
            if len(b' '.join(line)) > 510:
                raise ValueError('Cutscene command exceeds native GetToken line buffer')
            body.append(line); index += 1
        if index == len(lines):
            raise ValueError('Unclosed native cutscene block')
        rows.append((header[0], body)); index += 1
    if index != len(lines) - 1 or not rows or rows[0][0] != b'INIT_DATA' or any(name == b'INIT_DATA' for name, _ in rows[1:]):
        raise ValueError('Missing/duplicate native INIT_DATA')
    return rows


def _frame(body: list[bytes]) -> int:
    values = [i for i, token in enumerate(body) if token == b'FRAME']
    if len(values) != 1:
        raise ValueError('Cutscene node must have exactly one FRAME')
    try:
        result = int(body[values[0] + 1])
    except (IndexError, ValueError) as exc:
        raise ValueError('Malformed cutscene FRAME') from exc
    if not 0 <= result < 32767:
        raise ValueError('Cutscene FRAME exceeds native signed-short range')
    return result


def validate_cues(cues: Sequence[Mapping], *, camera_frames: int) -> list[dict]:
    """Never silently promote machine transcript drafts to accepted captions."""
    if type(camera_frames) is not int or not 2 <= camera_frames <= 32767:
        raise ValueError('Invalid source camera frame count')
    rows = []; ids = set()
    for cue in cues:
        row = dict(cue)
        if not isinstance(row.get('id'), str) or not row['id'] or row['id'] in ids:
            raise ValueError('Missing/duplicate subtitle cue ID')
        ids.add(row['id'])
        start, end = row.get('start_frame'), row.get('end_frame_exclusive')
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= camera_frames - 1:
            raise ValueError('Subtitle interval exceeds the source camera timeline')
        text = row.get('text')
        if not isinstance(text, str) or not text.strip() or any(c in text for c in '\0\r\n"'):
            raise ValueError('Empty/malformed subtitle text; use explicit <BR> for line breaks')
        if len(text.encode('utf8')) > 1000:
            raise ValueError('Subtitle text exceeds the bounded renderer input')
        if row.get('status') != 'reviewed':
            raise ValueError('Subtitle cue is not audio/transcript reviewed')
        if not re.fullmatch(r'[0-9a-f]{64}', row.get('source_audio_sha256', '')):
            raise ValueError('Subtitle cue needs a source-bound audio SHA-256')
        if not isinstance(row.get('source_transcript'), str) or not row['source_transcript'].strip():
            raise ValueError('Subtitle cue needs the reviewed source transcript')
        rows.append(row)
    rows.sort(key=lambda row: (row['start_frame'], row['id']))
    if len(rows) > 1024:
        raise ValueError('Too many captions for a cutscene')
    for left, right in zip(rows, rows[1:]):
        if left['end_frame_exclusive'] > right['start_frame']:
            raise ValueError('Subtitle intervals overlap')
    return rows


def inject_script(script: bytes, cues: Sequence[Mapping], encode: Callable[[str], bytes], *, camera_frames: int,
                  original_elf: bytes | None = None) -> tuple[bytes, dict]:
    """Stable-merge captions; remove proven ignored SOUND lines only if necessary."""
    rows = validate_cues(cues, camera_frames=camera_frames)
    source_tokens = _tokens(script); blocks = _line_blocks(script)
    if any(name == b'CAPTION' for name, _ in blocks) or b'CAPTION_COUNT' in source_tokens:
        raise ValueError('Expected retail script without an existing caption track')
    original_nodes = [(name, body, _frame([token for line in body for token in line])) for name, body in blocks[1:]]
    if any(a[2] > b[2] for a, b in zip(original_nodes, original_nodes[1:])):
        raise ValueError('Original cutscene nodes are not frame-sorted')
    if not rows:
        return script, {'source_sha256': sha(script), 'modified_sha256': sha(script), 'captions': 0, 'changed': False}
    if len(original_nodes) + len(rows) > 32767:
        raise ValueError('Native cutscene node count overflow')
    inserted = []
    for row in rows:
        raw = encode(row['text'])
        if not raw or len(raw) > 480 or any(c in raw for c in (0, 10, 13, 34)):
            raise ValueError('Subtitle encoding is not a valid quoted SCR value')
        # The paired engine patch changes only the previously-unused caption
        # defaults to 40/350, saving a POSITION command in every constrained SCR.
        body = [[b'FRAME', str(row['start_frame']).encode()],
                [b'CONTENTS', str(row['end_frame_exclusive'] - row['start_frame']).encode(), b'"' + raw + b'"']]
        inserted.append((b'CAPTION', body, row['start_frame']))
    init = blocks[0][1] + [[b'CAPTION_COUNT', str(len(rows)).encode()]]

    def render(nodes):
        # Existing equal-frame nodes retain their order; captions follow them.
        merged = [(name, body, frame, 0, i) for i, (name, body, frame) in enumerate(nodes)]
        merged += [(name, body, frame, 1, i) for i, (name, body, frame) in enumerate(inserted)]
        merged.sort(key=lambda row: (row[2], row[3], row[4]))
        lines = [[b'SCR_TYPE', b'CUTSCENE'], [b'INIT_DATA', b'{'], *init, [b'}']]
        for name, body, *_ in merged:
            lines += [[name, b'{'], *body, [b'}']]
        return b'\r\n'.join(b' '.join(line) for line in lines + [[b'END']]) + b'\r\n'

    result = render(original_nodes)
    full_candidate_size = len(result)
    removed = []; position_proof = None
    if len(result) > len(script) and original_elf is not None:
        position_proof = inspect_sound_position_elision(original_elf)
        compact_nodes = []
        for node_index, (name, body, frame) in enumerate(original_nodes):
            types = [line for line in body if line[0] == b'SOUND_TYPE']
            positions = [(i, line) for i, line in enumerate(body) if line[0] == b'POSITION']
            if (name == b'SOUND' and len(types) == 1 and len(types[0]) == 3
                    and types[0][1] in (b'BGM', b'VOICE') and len(positions) == 1
                    and positions[0][1] == [b'POSITION', b'0', b'0', b'0']):
                index, line = positions[0]
                removed.append({'node_index': node_index, 'command_index': index,
                                'block': 'SOUND', 'frame': frame, 'sound_type': types[0][1].decode('ascii'),
                                'name_tokens_hex': [[token.hex() for token in command] for command in body if command[0] == b'NAME'],
                                'tokens_hex': [token.hex() for token in line], 'bytes_saved': 16})
                body = [command for i, command in enumerate(body) if i != index]
            compact_nodes.append((name, body, frame))
        result = render(compact_nodes)
    if len(result) > len(script):
        raise ValueError(f'Caption SCR exceeds original member capacity: {len(result)} > {len(script)}')
    content_size = len(result)
    result = result.ljust(len(script), b' ')
    # Independent readback reverses additions AND only the declared ignored lines,
    # then requires every original node/command/value/order to match exactly.
    parsed = _line_blocks(result); restored_init = parsed[0][1][:-1]
    restored_nodes = [(name, body) for name, body in parsed[1:] if name != b'CAPTION']
    for omitted in removed:
        name, body = restored_nodes[omitted['node_index']]
        body.insert(omitted['command_index'], [bytes.fromhex(token) for token in omitted['tokens_hex']])
    if restored_init != blocks[0][1] or restored_nodes != blocks[1:]:
        raise AssertionError('Caption injection altered original cutscene semantics')
    return result, {
        'source_sha256': sha(script), 'modified_sha256': sha(result), 'source_size': len(script),
        'captions': len(rows), 'original_nodes': len(original_nodes),
        'original_tokens_retained': not removed, 'original_semantics_retained': True,
        'retail_GetToken_command_lines_retained': True,
        'full_candidate_size': full_candidate_size, 'content_size': content_size,
        'padding_bytes': len(script) - content_size, 'removed_ignored_commands': removed,
        'ignored_command_bytes_saved': sum(row['bytes_saved'] for row in removed),
        'ignored_sound_position_proof': position_proof,
        'same_frame_order': 'original nodes first, original relative order retained',
        'camera_frames': camera_frames, 'cues': rows, 'changed': True,
    }


def inventory(image) -> list[dict]:
    """Read all 47 retail cutscene SCR/camera identities, without copying assets."""
    rows = []; cameras = {}
    for path in sorted(image.files):
        if not path.startswith('RES/CUTSCENE/') or not path.endswith('.RES'):
            continue
        archive = parse_res(image.read(path))
        for camera_member in archive.entries:
            if re.fullmatch(r'C\d{3}\.BIN', camera_member.name):
                scene = camera_member.name[:-4]
                if scene in cameras:
                    raise ValueError('Duplicate cutscene camera member')
                cameras[scene] = (path, camera_member.name, archive.read(camera_member))
        scripts = [member for member in archive.entries if re.fullmatch(r'C\d{3}\.SCR', member.name)]
        if not scripts:
            continue  # Split geometry-only RES companions contain no timeline.
        if len(scripts) != 1:
            raise ValueError('Unexpected cutscene script member closure: ' + path)
        member = scripts[0]; source = archive.read(member); blocks = _line_blocks(source)
        scene = member.name[:-4]
        nodes = [(name, body, _frame([token for line in body for token in line])) for name, body in blocks[1:]]
        if any(a[2] > b[2] for a, b in zip(nodes, nodes[1:])):
            raise ValueError('Non-monotonic source cutscene node order')
        rows.append({'scene': scene, 'resource': path, 'member': member.name,
                     'source_sha256': sha(source), 'source_size': len(source),
                     'native_captions': sum(name == b'CAPTION' for name, _, _ in nodes),
                     'node_count': len(nodes), 'last_node_frame': max((n[2] for n in nodes), default=0)})
    expected_scenes = {f'C{i:03d}' for i in range(1, 48)}
    if {row['scene'] for row in rows} != expected_scenes or len(rows) != 47 or set(cameras) != expected_scenes:
        raise ValueError('Cutscene scene closure changed')
    for row in rows:
        path, member_name, camera = cameras[row['scene']]
        if len(camera) < 10:
            raise ValueError('Truncated cutscene camera')
        magic, frames, positions, directions, updirs = struct.unpack_from('<5H', camera)
        if magic != 1001 or len(camera) != 10 + 12 * (positions + directions + updirs):
            raise ValueError('Unexpected cutscene camera arrays')
        row.update(camera_resource=path, camera_member=member_name, camera_sha256=sha(camera), camera_frames=frames)
    return rows


def validate_catalogue(image, catalogue: Mapping, *, locale: str | None = None) -> list[dict]:
    """Validate source/timing/review before font allocation or any output writes."""
    if (catalogue.get('format') != 'cutscene-subtitle-catalogue' or catalogue.get('version') != 1
            or catalogue.get('source_iso_sha256') != ORIGINAL_ISO_SHA256):
        raise ValueError('Unsupported/source-mismatched cutscene subtitle catalogue')
    if locale is not None and catalogue.get('locale') != locale:
        raise ValueError('Cutscene subtitle locale mismatch')
    source_rows = {row['scene']: row for row in inventory(image)}
    supplied = catalogue.get('resources')
    if not isinstance(supplied, list):
        raise ValueError('Missing cutscene subtitle resources')
    rows = {}
    for row in supplied:
        if not isinstance(row, dict) or row.get('scene') in rows:
            raise ValueError('Duplicate/malformed subtitle scene')
        rows[row.get('scene')] = row
    if set(rows) != set(source_rows):
        raise ValueError('Subtitle catalogue must enumerate every retail cutscene')
    validated = []; total = 0
    for scene, source in source_rows.items():
        row = rows[scene]
        for field in ['resource', 'member', 'source_sha256', 'source_size', 'camera_resource', 'camera_member', 'camera_sha256', 'camera_frames']:
            if row.get(field) != source[field]:
                raise ValueError(f'Cutscene subtitle source identity mismatch: {scene}/{field}')
        cues = row.get('cues')
        if not isinstance(cues, list):
            raise ValueError('Subtitle scene needs an explicit cues list')
        checked = validate_cues(cues, camera_frames=source['camera_frames'])
        validated.append({**source, 'cues': checked}); total += len(checked)
    if total == 0:
        raise ValueError('Explicit subtitle catalogue has no reviewed cues')
    return validated


def build_script_edits(image, catalogue: Mapping, mapping: Mapping[str, int]) -> tuple[dict[str, dict[tuple[int, int], bytes]], dict]:
    """Build reviewed caption member edits; caller merges them with other RES edits.

    The catalogue must enumerate the full retail scene closure. A machine draft
    anywhere in its cues fails rather than being silently skipped. Empty cues
    are inventory entries, not a declaration that the scene is fully subtitled.
    """
    source_rows = validate_catalogue(image, catalogue)
    original_elf = image.read('SCKA_200.55')
    edits = {}; reports = []; total = 0
    for source in source_rows:
        scene = source['scene']; cues = source['cues']
        archive = parse_res(image.read(source['resource'])); member = archive.get(source['member'])
        replacement, detail = inject_script(archive.read(member), cues, lambda text: encode_text(text, mapping),
                                            camera_frames=source['camera_frames'], original_elf=original_elf)
        if replacement != archive.read(member):
            edits.setdefault(source['resource'], {})[member.key] = replacement
        reports.append({'scene': scene, 'resource': source['resource'], 'member': source['member'], **detail})
        total += detail['captions']
    return edits, {'format': 'cutscene-subtitle-script-edits', 'version': 1, 'source_iso_sha256': ORIGINAL_ISO_SHA256,
                   'scenes': len(source_rows), 'captioned_scenes': len(edits), 'reviewed_cues': total,
                   'reports': reports, 'all_speech_transcribed': False, 'runtime_acceptance': 'pending player test'}


@dataclass
class _Unit:
    words: list[int]
    branch: tuple[int, int, int, str] | None = None


class _Assembler:
    def __init__(self):
        self.units: list[_Unit] = []; self.labels: dict[str, int] = {}

    def label(self, name):
        if name in self.labels:
            raise ValueError('Duplicate assembler label')
        self.labels[name] = len(self.units)

    def word(self, word):
        self.units.append(_Unit([word]))

    def imm(self, op, rt, rs, value):
        self.word(op << 26 | rs << 21 | rt << 16 | (value & 65535))

    def reg(self, op, rd, rs, rt):
        self.word(rs << 21 | rt << 16 | rd << 11 | op)

    def branch(self, op, rs, rt, name):
        self.units.append(_Unit([0, 0], (op, rs, rt, name)))

    def call(self, address):
        self.units.append(_Unit([3 << 26 | address >> 2, 0]))

    def ret(self):
        self.units.append(_Unit([31 << 21 | 8, 0]))

    def address(self, register, address):
        self.imm(15, register, 0, address >> 16)
        self.imm(13, register, register, address & 65535)


def _renderer() -> _Assembler:
    """MIPS/EE ABI hook; caller-saved registers may change, full saved GPRs do not."""
    a = _Assembler()
    # s0=cutscene, s1=node cursor, s2=remaining, s3=draw frame, s4=selected caption.
    a.imm(9, 29, 29, -0x90)
    for reg, offset in [(31, 0), (16, 16), (17, 32), (18, 48), (19, 64), (20, 80)]:
        a.imm(31, reg, 29, offset)  # EE SQ preserves all 128 bits
    a.address(16, CUTSCENE_ADDRESS)
    a.imm(32, 2, 16, 0x3F0); a.branch(5, 2, 0, 'flip')  # skip => no caption
    a.imm(33, 19, 16, 2); a.imm(9, 19, 19, -1)
    a.branch(1, 19, 0, 'flip')  # BLTZ draw_frame
    a.imm(33, 18, 16, 0x3F6); a.branch(6, 18, 0, 'flip')
    a.imm(33, 2, 16, 0x414); a.branch(6, 2, 0, 'flip')
    a.imm(35, 17, 16, 0x3F8); a.branch(4, 17, 0, 'flip')
    a.imm(35, 2, 16, 0x41C); a.branch(4, 2, 0, 'flip')
    a.imm(9, 20, 0, 0)
    a.label('node')
    a.imm(37, 2, 17, 0); a.imm(9, 3, 0, 2); a.branch(5, 2, 3, 'next')
    a.imm(33, 2, 17, 4); a.reg(42, 3, 19, 2); a.branch(5, 3, 0, 'next')
    a.imm(37, 2, 17, 2); a.imm(33, 3, 16, 0x414)
    a.reg(43, 3, 2, 3); a.branch(4, 3, 0, 'next')
    a.word(2 << 16 | 3 << 11 | 1 << 6)  # sll v1,v0,1
    a.reg(33, 3, 3, 2); a.word(3 << 16 | 3 << 11 | 3 << 6)
    a.imm(35, 2, 16, 0x41C); a.reg(33, 2, 2, 3)
    a.imm(33, 3, 2, 12); a.reg(42, 3, 3, 19); a.branch(5, 3, 0, 'next')
    a.imm(35, 3, 2, 8); a.branch(4, 3, 0, 'next')
    a.reg(33, 20, 2, 0)
    a.label('next')
    a.imm(9, 17, 17, 6); a.imm(9, 18, 18, -1); a.branch(7, 18, 0, 'node')
    a.branch(4, 20, 0, 'flip')
    # FontEnv is exactly 32 bytes in the original DWARF; preserve both QWs.
    a.address(3, FONT_ENV_ADDRESS)
    a.imm(30, 2, 3, 0); a.imm(31, 2, 29, 0x60)
    a.imm(30, 2, 3, 16); a.imm(31, 2, 29, 0x70)
    a.call(FONT_RESET_ADDRESS)
    a.imm(9, 4, 0, 1); a.imm(9, 5, 0, 128); a.call(ALPHA_MODE_ADDRESS)
    # Use RenderString, not a printf-style wrapper: literal % is never expanded.
    for shadow in [True, False]:
        for reg in [4, 5, 6]:
            a.imm(9, reg, 0, 0 if shadow else 128)
        a.imm(9, 7, 0, 128); a.call(FONT_COLOR_ADDRESS)
        a.imm(33, 4, 20, 2); a.imm(33, 5, 20, 4)
        if shadow:
            a.imm(9, 4, 4, 2); a.imm(9, 5, 5, 2)
        a.imm(9, 6, 0, 550); a.imm(35, 7, 20, 8); a.call(RENDER_STRING_ADDRESS)
    a.address(3, FONT_ENV_ADDRESS)
    a.imm(30, 2, 29, 0x60); a.imm(31, 2, 3, 0)
    a.imm(30, 2, 29, 0x70); a.imm(31, 2, 3, 16)
    a.label('flip'); a.call(FLIP_ADDRESS)
    for reg, offset in [(31, 0), (16, 16), (17, 32), (18, 48), (19, 64), (20, 80)]:
        a.imm(30, reg, 29, offset)
    a.imm(9, 29, 29, 0x90); a.ret()
    return a


def _padding_slots(original: bytes, current: bytes, entries: Sequence[Mapping], mapping: Mapping[str, int]) -> list[dict]:
    slots = []; used = []
    for row in entries:
        if row.get('kind') != 'elf' or row.get('resource') != 'SCKA_200.55' or not row.get('target'):
            continue
        offset, capacity = row['offset'], row['capacity']
        if type(offset) is not int or type(capacity) is not int or offset < 0 or capacity < 1 or offset + capacity > len(current):
            raise ValueError('Malformed caption code-padding owner')
        if sha(original[offset:offset + capacity]) != row['source_sha256']:
            raise ValueError('Caption code-padding owner source mismatch')
        target = encode_text(row['target'], mapping) + b'\0'
        if current[offset:offset + len(target)] != target:
            raise ValueError('Caption code-padding owner translation mismatch')
        start = (offset + len(target) + 3) & ~3; end = (offset + capacity) & ~3
        if end - start < 32 or any(current[offset + len(target):offset + capacity]):
            continue  # The existing lookahead table, for example, is not free.
        if any(not (end <= lo or hi <= start) for lo, hi in used):
            raise ValueError('Overlapping caption code-padding owners')
        used.append((start, end))
        address = _offset_address(original, start, end - start)
        slots.append({'owner_id': row['id'], 'offset': start, 'capacity': end - start,
                      'address': address, 'first_nul_offset': offset + len(target) - 1,
                      'source_owner_offset': offset, 'source_owner_capacity': capacity,
                      'source_owner_sha256': row['source_sha256']})
    return sorted(slots, key=lambda slot: (-slot['capacity'], slot['owner_id']))


def _offset_address(elf: bytes, offset: int, size: int) -> int:
    phoff = struct.unpack_from('<I', elf, 28)[0]; stride, count = struct.unpack_from('<HH', elf, 42)
    matches = []
    for index in range(count):
        kind, start, va, _, length, _, flags, _ = struct.unpack_from('<8I', elf, phoff + index * stride)
        if kind == 1 and flags & 1 and start <= offset and offset + size <= start + length:
            matches.append(va + offset - start)
    if len(matches) != 1:
        raise ValueError('Caption padding is outside uniquely mapped executable memory')
    return matches[0]


def build_engine_patch(original: bytes, current: bytes, entries: Sequence[Mapping], mapping: Mapping[str, int]) -> tuple[bytes, dict]:
    """Return an independent guarded ELF edit; the normal builder opts in explicitly."""
    evidence = inspect_engine(original)
    if len(current) != len(original) or current[:128] != original[:128]:
        raise ValueError('Caption input ELF load layout changed')
    for row in evidence['anchors']:
        raw = bytes.fromhex(row['expected_hex']); p = row['offset']
        if current[p:p + len(raw)] != raw:
            raise ValueError('Current caption engine anchor mismatch')
    assembler = _renderer(); slots = _padding_slots(original, current, entries, mapping)
    chunks = []; index = 0; addresses = {}
    for slot in slots:
        if index == len(assembler.units):
            break
        room = slot['capacity'] // 4 - 2; units = []; words = 0
        while index < len(assembler.units) and words + len(assembler.units[index].words) <= room:
            addresses[index] = slot['address'] + words * 4
            units.append(index); words += len(assembler.units[index].words); index += 1
        if units:
            chunks.append({**slot, 'unit_indices': units, 'word_count': words})
    if index != len(assembler.units):
        raise ValueError('Insufficient verified post-NUL string padding for caption code')
    labels = {name: addresses[index] for name, index in assembler.labels.items()}
    output = bytearray(current); writes = []
    for ci, chunk in enumerate(chunks):
        words = []
        for unit_index in chunk['unit_indices']:
            unit = assembler.units[unit_index]; emitted = unit.words[:]
            if unit.branch:
                op, rs, rt, target = unit.branch
                delta = (labels[target] - addresses[unit_index] - 4) // 4
                if not -32768 <= delta <= 32767:
                    raise ValueError('Caption branch exceeds signed-short range')
                emitted[0] = op << 26 | rs << 21 | rt << 16 | (delta & 65535)
            words += emitted
        if ci + 1 < len(chunks):
            words += [2 << 26 | chunks[ci + 1]['address'] >> 2, 0]
        payload = struct.pack('<' + 'I' * len(words), *words)
        p = chunk['offset']; before = current[p:p + len(payload)]
        if any(before) or len(payload) > chunk['capacity']:
            raise AssertionError('Caption code escaped its verified zero padding')
        output[p:p + len(payload)] = payload
        writes.append({'offset': p, 'address': chunk['address'], 'owner_id': chunk['owner_id'],
                       'before': before.hex(), 'after': payload.hex()})
    hook_offset = address_offset(original, HOOK_ADDRESS)
    hook = struct.pack('<I', 3 << 26 | chunks[0]['address'] >> 2)
    output[hook_offset:hook_offset + 4] = hook
    writes.append({'offset': hook_offset, 'address': HOOK_ADDRESS,
                   'before': current[hook_offset:hook_offset + 4].hex(), 'after': hook.hex()})
    for address, register, value in CAPTION_DEFAULTS:
        offset = address_offset(original, address)
        payload = struct.pack('<I', 9 << 26 | register << 16 | value)
        output[offset:offset + 4] = payload
        writes.append({'offset': offset, 'address': address, 'before': current[offset:offset + 4].hex(), 'after': payload.hex()})
    report = {'format': 'mips-frame-cutscene-captions', 'version': 1,
              'source_sha256': sha(original), 'before_sha256': sha(current), 'after_sha256': sha(output),
              'size': len(current), 'entry_address': chunks[0]['address'], 'hook_address': HOOK_ADDRESS,
              'labels': labels, 'padding_owners': chunks, 'writes': sorted(writes, key=lambda row: row['offset']),
              'caption_default_position': [40, 350],
              'engine_evidence': evidence, 'game_executed': False,
              'transcript_gate': 'only independently audio-reviewed cues are accepted by inject_script'}
    return bytes(output), report


def reverse_engine_patch(current: bytes, report: Mapping) -> bytes:
    if report.get('format') != 'mips-frame-cutscene-captions' or report.get('version') != 1 or len(current) != report['size'] or sha(current) != report['after_sha256']:
        raise ValueError('Caption rollback input identity mismatch')
    output = bytearray(current); end = -1
    for row in report['writes']:
        p = row['offset']; before, after = bytes.fromhex(row['before']), bytes.fromhex(row['after'])
        if p < end or len(before) != len(after) or p < 0 or p + len(after) > len(current) or current[p:p + len(after)] != after:
            raise ValueError('Caption rollback range mismatch')
        output[p:p + len(before)] = before; end = p + len(before)
    if sha(output) != report['before_sha256']:
        raise ValueError('Caption rollback result identity mismatch')
    return bytes(output)


def replay_engine_hook(elf: bytes, report: Mapping, *, frame: int, nodes: Sequence[Mapping],
                       captions: Sequence[Mapping], skip=False) -> dict:
    """Execute generated scalar/EE-load-store words in a bounded offline fixture.

    Native text/Flip calls are explicit contract stubs, not rendering or PS2
    execution. Branch delay slots, fragmented-code bridges, signed frame tests,
    128-bit callee saves, font state and the one original Flip are checked.
    """
    if report.get('format') != 'mips-frame-cutscene-captions' or sha(elf) != report['after_sha256']:
        raise ValueError('Caption replay image identity mismatch')
    if type(frame) is not int or not -32768 <= frame <= 32767 or len(nodes) > 32767 or len(captions) > 32767:
        raise ValueError('Caption replay native-short input overflow')
    memory = {}; mask64 = (1 << 64) - 1; mask128 = (1 << 128) - 1

    def put(address, size, value):
        data = value.to_bytes(size, 'little') if isinstance(value, int) else bytes(value)
        if len(data) != size:
            raise ValueError('Fixture byte count mismatch')
        for index, value in enumerate(data):
            memory[address + index] = value

    def get(address, size):
        return bytes(memory.get(address + index, 0) for index in range(size))

    def number(address, size, *, signed=False):
        return int.from_bytes(get(address, size), 'little', signed=signed)

    def signed(value, bits=64):
        value &= (1 << bits) - 1
        return value - (1 << bits) if value >> (bits - 1) else value

    def write(register, value):
        if register:
            registers[register] = registers[register] & (mask128 ^ mask64) | value & mask64

    def cstring(address):
        result = bytearray()
        for index in range(1024):
            value = number(address + index, 1)
            if not value:
                return bytes(result)
            result.append(value)
        raise ValueError('Fixture renderer string was not bounded')

    registers = [((0xABC00000 + i) << 96) | ((0x45600000 + i) << 32) | (0x1000 + i) for i in range(32)]
    registers[0] = 0; registers[29] = 0x1F00000; registers[31] = 0xF00000
    saved = {index: registers[index] for index in [16, 17, 18, 19, 20, 21, 22, 23, 28, 29, 31]}
    put(CUTSCENE_ADDRESS, 1136, bytes(1136))
    put(CUTSCENE_ADDRESS + 2, 2, frame & 65535)
    put(CUTSCENE_ADDRESS + 0x3F0, 1, int(bool(skip)))
    put(CUTSCENE_ADDRESS + 0x3F6, 2, len(nodes))
    put(CUTSCENE_ADDRESS + 0x3F8, 4, 0x400000)
    put(CUTSCENE_ADDRESS + 0x414, 2, len(captions))
    put(CUTSCENE_ADDRESS + 0x41C, 4, 0x410000)
    for index, node in enumerate(nodes):
        put(0x400000 + 6 * index, 6, struct.pack('<3h', node['type'], node['index'], node['frame']))
    for index, caption in enumerate(captions):
        pointer = 0x420000 + index * 1024; text = caption['text']
        if not isinstance(text, bytes) or len(text) > 510 or b'\0' in text:
            raise ValueError('Invalid fixture caption bytes')
        put(pointer, len(text) + 1, text + b'\0')
        raw = bytearray(24)
        struct.pack_into('<hh', raw, 2, caption.get('x', 40), caption.get('y', 350))
        struct.pack_into('<Ih', raw, 8, pointer, caption['end_frame_inclusive'])
        put(0x410000 + index * 24, 24, raw)
    original_font_env = bytes((index * 7 + 3) & 255 for index in range(32))
    put(FONT_ENV_ADDRESS, 32, original_font_env)
    external_calls = []; draws = []; pc = report['entry_address']; pending = None
    external_addresses = {FONT_RESET_ADDRESS, FONT_COLOR_ADDRESS, RENDER_STRING_ADDRESS, ALPHA_MODE_ADDRESS, FLIP_ADDRESS}
    allowed_code = [(row['address'], row['address'] + len(bytes.fromhex(row['after'])))
                    for row in report['writes'] if 'owner_id' in row]
    steps = 0
    while steps < 250000:
        steps += 1
        if pc == saved[31]:
            if any(registers[index] != value for index, value in saved.items()):
                raise AssertionError('Caption hook corrupted saved GPR/stack state')
            if get(FONT_ENV_ADDRESS, 32) != original_font_env:
                raise AssertionError('Caption hook leaked font environment state')
            if external_calls.count(FLIP_ADDRESS) != 1:
                raise AssertionError('Caption hook did not execute exactly one original Flip')
            return {'draws': draws, 'flip_calls': 1, 'font_environment_restored': True,
                    'saved_registers_128bit_restored': True, 'steps': steps,
                    'draw_frame': frame - 1, 'external_calls_stubbed': True, 'game_executed': False}
        if pc in external_addresses:
            external_calls.append(pc)
            if pc == FONT_RESET_ADDRESS:
                put(FONT_ENV_ADDRESS, 32, bytes(32))
            elif pc == FONT_COLOR_ADDRESS:
                put(FONT_ENV_ADDRESS + 4, 8, struct.pack('<4H', *(registers[i] & 65535 for i in [4, 5, 6, 7])))
            elif pc == RENDER_STRING_ADDRESS:
                draws.append({'x': signed(registers[4]), 'y': signed(registers[5]),
                              'width': signed(registers[6]), 'text_hex': cstring(registers[7] & mask64).hex(),
                              'rgba': list(struct.unpack('<4H', get(FONT_ENV_ADDRESS + 4, 8)))})
            return_address = registers[31] & mask64
            for reg in [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 24, 25]:
                write(reg, 0xA0B00000 + reg)
            write(2, 0x12345678 if pc == FLIP_ADDRESS else 0)
            pc = return_address
            continue
        if not any(lo <= pc < hi for lo, hi in allowed_code) or pc % 4:
            raise ValueError(f'Caption fixture PC escaped generated code: {pc:#x}')
        offset = address_offset(elf, pc)
        word = struct.unpack_from('<I', elf, offset)[0]
        opcode, rs, rt, rd, shift, function = word >> 26, word >> 21 & 31, word >> 16 & 31, word >> 11 & 31, word >> 6 & 31, word & 63
        immediate = word & 65535; simm = signed(immediate, 16)
        before_pending = pending; pending = None; destination = None
        if word == 0:
            pass
        elif opcode == 0:
            left, right = registers[rs] & mask64, registers[rt] & mask64
            if function == 0:
                write(rd, signed((right & 0xFFFFFFFF) << shift, 32))
            elif function == 33:
                write(rd, signed(left + right, 32))
            elif function == 42:
                write(rd, int(signed(left) < signed(right)))
            elif function == 43:
                write(rd, int(left < right))
            elif function == 8:
                destination = left
            else:
                raise ValueError(f'Unsupported caption scalar fixture instruction: {word:08x}')
        elif opcode == 9:
            write(rt, signed(registers[rs] + simm, 32))
        elif opcode == 15:
            write(rt, signed(immediate << 16, 32))
        elif opcode == 13:
            write(rt, (registers[rs] & mask64) | immediate)
        elif opcode in (30, 31, 32, 33, 35, 37):
            address = ((registers[rs] & mask64) + simm) & mask64
            if opcode == 31:
                put(address, 16, registers[rt])
            elif opcode == 30:
                registers[rt] = number(address, 16)
            else:
                size = {32: 1, 33: 2, 35: 4, 37: 2}[opcode]
                write(rt, number(address, size, signed=opcode != 37))
        elif opcode in (1, 4, 5, 6, 7):
            left, right = registers[rs] & mask64, registers[rt] & mask64
            taken = {1: signed(left) < 0, 4: left == right, 5: left != right,
                     6: signed(left) <= 0, 7: signed(left) > 0}[opcode]
            destination = pc + 4 + simm * 4 if taken else pc + 8
        elif opcode in (2, 3):
            destination = (pc + 4) & 0xF0000000 | (word & 0x3FFFFFF) * 4
            if opcode == 3:
                write(31, pc + 8)
        else:
            raise ValueError(f'Unsupported caption fixture opcode: {word:08x}')
        if before_pending is not None:
            if destination is not None:
                raise ValueError('A caption branch appeared in a branch delay slot')
            pc = before_pending
        else:
            pc += 4
            pending = destination
        registers[0] = 0
    raise ValueError('Caption replay instruction bound exceeded')
