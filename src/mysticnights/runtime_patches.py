"""Version-bound, optional PCSX2 patches, kept separate from disc localization."""
import hashlib
import json
import struct
from pathlib import Path


def pcsx2_crc(data: bytes) -> str:
    """ElfObject::GetCRC: XOR complete little-endian words, not CRC-32."""
    value = 0
    for (word,) in struct.iter_unpack('<I', data[:len(data) // 4 * 4]):
        value ^= word
    return f'{value:08X}'


def address_offset(elf: bytes, address: int, size: int = 4) -> int:
    if elf[:7] != b'\x7fELF\x01\x01\x01' or len(elf) < 52:
        raise ValueError('Expected ELF32 little endian')
    phoff = struct.unpack_from('<I', elf, 28)[0]
    stride, count = struct.unpack_from('<HH', elf, 42)
    if stride != 32 or phoff + stride * count > len(elf):
        raise ValueError('Invalid ELF program header table')
    for i in range(count):
        kind, offset, va, _, length, _, flags, _ = struct.unpack_from('<8I', elf, phoff + i * stride)
        if kind == 1 and flags & 1 and va <= address and address + size <= va + length:
            start = offset + address - va
            if start + size <= len(elf):
                return start
    raise ValueError('Runtime patch is outside file-backed executable memory')


def validate_recipe(original: bytes, current: bytes, recipe: dict) -> None:
    if (recipe.get('format') != 'mips-runtime-patches' or recipe.get('version') != 1
            or len(original) != recipe['source_size'] or len(current) != len(original)
            or hashlib.sha256(original).hexdigest() != recipe['source_sha256']
            or pcsx2_crc(original) != recipe['source_crc']):
        raise ValueError('Runtime patch source identity mismatch')
    if current[:52] != original[:52]:
        raise ValueError('Runtime ELF executable layout changed')
    used = set()
    identifiers = set()
    for group in recipe['groups']:
        if group['id'] in identifiers or group['kind'] not in ('patches', 'cheats'):
            raise ValueError('Duplicate/invalid runtime patch group')
        identifiers.add(group['id'])
        for edit in group['writes']:
            address = int(edit['address'], 16)
            offset = address_offset(original, address)
            if address_offset(current, address) != offset:
                raise ValueError('Runtime ELF load mapping changed')
            if address % 4 or address in used:
                raise ValueError('Unaligned/overlapping runtime patch')
            used.add(address)
            before = struct.pack('<I', int(edit['before'], 16))
            after = struct.pack('<I', int(edit['after'], 16))
            if before == after or original[offset:offset + 4] != before or current[offset:offset + 4] != before:
                raise ValueError(f'Runtime instruction anchor mismatch: {edit["address"]}')


def patch_fixture(original: bytes, current: bytes, recipe: dict, selected: set[str], *, reverse=False) -> bytes:
    """Offline copy only; every expected word is guarded, including rollback."""
    ids = {g['id'] for g in recipe['groups']}
    if not selected <= ids:
        raise ValueError('Unknown runtime patch group')
    restored = bytearray(current)
    if reverse:
        for group in recipe['groups']:
            if group['id'] in selected:
                for edit in group['writes']:
                    offset = address_offset(original, int(edit['address'], 16))
                    before, after = [struct.pack('<I', int(edit[k], 16)) for k in ('before', 'after')]
                    if restored[offset:offset + 4] != after:
                        raise ValueError('Runtime rollback instruction mismatch')
                    restored[offset:offset + 4] = before
        validate_recipe(original, bytes(restored), recipe)
        return bytes(restored)
    validate_recipe(original, current, recipe)
    for group in recipe['groups']:
        if group['id'] in selected:
            for edit in group['writes']:
                offset = address_offset(original, int(edit['address'], 16))
                restored[offset:offset + 4] = struct.pack('<I', int(edit['after'], 16))
    return bytes(restored)


def render_package(original: bytes, current: bytes, recipe: dict, labels: dict) -> tuple[dict[str, bytes], dict]:
    validate_recipe(original, current, recipe)
    if set(labels['groups']) != {g['id'] for g in recipe['groups']}:
        raise ValueError('Runtime patch translation coverage mismatch')
    files = {}
    identities = [('original', original), ('localized', current)]
    records = []
    for role, elf in identities:
        crc = pcsx2_crc(elf)
        for kind in ('patches', 'cheats'):
            rows = [f'gametitle={labels["game_title"]}',
                    f'// {role} ELF SHA256 {hashlib.sha256(elf).hexdigest()}',
                    '// Optional groups. Disable and cold boot to restore original behavior.', '']
            for group in recipe['groups']:
                if group['kind'] != kind:
                    continue
                label = labels['groups'][group['id']]
                if any(c in label['name'] + label['description'] for c in '\r\n[]'):
                    raise ValueError('Invalid runtime patch label')
                rows += [f'[{label["name"]}]', f'description={label["description"]}']
                if 'author' in group:
                    rows.append(f'author={group["author"]}')
                if group['id'] == 'widescreen-16-9':
                    rows.append('gsaspectratio=16:9')
                rows += [f'patch=1,EE,{w["address"]},word,{w["after"]} // original {w["before"]}' for w in group['writes']]
                rows.append('')
            filename = f'{role}/{kind}/{recipe["serial"]}_{crc}.pnach'
            files[filename] = ('\n'.join(rows) + '\n').encode('utf8')
        records.append({'role': role, 'elf_sha256': hashlib.sha256(elf).hexdigest(), 'crc': crc})
    report = {'format': 'runtime-patch-package', 'version': 1, 'recipe': recipe, 'identities': records,
              'files': [{'path': k, 'size': len(v), 'sha256': hashlib.sha256(v).hexdigest()} for k, v in sorted(files.items())],
              'validation': 'source-byte guards and isolated instruction fixtures; user performs in-game acceptance'}
    files['manifest.json'] = (json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode('utf8')
    return files, report


def write_package(directory: Path, files: dict[str, bytes]) -> None:
    if directory.exists():
        raise FileExistsError('Runtime output already exists')
    directory.mkdir(parents=True)
    for name, data in files.items():
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        if target.read_bytes() != data:
            raise ValueError('Runtime patch file readback mismatch')
