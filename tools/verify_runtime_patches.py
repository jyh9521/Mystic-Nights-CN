"""Offline instruction fixtures; never opens an emulator or attaches to a game."""
import argparse
import itertools
import json
import math
import struct
from pathlib import Path
from _bootstrap import ROOT
from mysticnights.versions import verify_original, load_version
from mysticnights.iso9660 import IsoImage, sha256_file
from mysticnights.runtime_patches import address_offset, pcsx2_crc, validate_recipe, patch_fixture


def word(elf, address):
    return struct.unpack_from('<I', elf, address_offset(elf, address))[0]


def execute_store(instruction, value, initial):
    """Actual source SB/SH or emitted NOP, against isolated synthetic memory."""
    memory = bytearray(b'\x5a' * 256)
    if instruction == 0:
        return initial
    op, offset = instruction >> 26, instruction & 0xffff
    if op not in (0x28, 0x29) or offset > 254:
        raise ValueError('Unexpected store fixture instruction')
    width = 1 if op == 0x28 else 2
    memory[offset:offset+width] = initial.to_bytes(width, 'little')
    memory[offset:offset+width] = (value & ((1 << (width*8))-1)).to_bytes(width, 'little')
    return int.from_bytes(memory[offset:offset+width], 'little')


def verify_fixtures(original, current, recipe):
    validate_recipe(original, current, recipe)
    ids = [g['id'] for g in recipe['groups']]
    for flags in itertools.product((False, True), repeat=len(ids)):
        selected = {k for k, yes in zip(ids, flags) if yes}
        edited = patch_fixture(original, current, recipe, selected)
        if patch_fixture(original, edited, recipe, selected, reverse=True) != current:
            raise ValueError('Runtime fixture rollback differs from localized ELF')
    modified = patch_fixture(original, current, recipe, set(ids))
    store_cases = 0
    for group in recipe['groups']:
        if group['id'] not in ('infinite-ammo', 'infinite-health'):
            continue
        for edit in group['writes']:
            address = int(edit['address'], 16)
            old_word, new_word = word(current, address), word(modified, address)
            for initial in (1, 2, 7, 30, 100):
                # The new instructions do not write; normal damage/consumption
                # values are inputs to the store fixture, not a playthrough.
                for decrement in (1, min(initial, 7)):
                    before = execute_store(old_word, initial-decrement, initial)
                    after = execute_store(new_word, initial-decrement, initial)
                    if before != initial-decrement or after != initial:
                        raise ValueError('Consumption/damage store fixture failed')
                    store_cases += 1
    def f32(value):return struct.unpack('<f', struct.pack('<f', value))[0]
    def step(elf, address):
        high, low = word(elf, address), word(elf, address+4)
        if high >> 26 != 15 or low >> 26 != 13:
            raise ValueError('Yaw constant is not a guarded LUI/ORI pair')
        return struct.unpack('<f', struct.pack('<I', (high & 65535) << 16 | low & 65535))[0]
    pi = struct.unpack('<f', bytes.fromhex('d80f4940'))[0]
    two_pi = struct.unpack('<f', bytes.fromhex('d80fc940'))[0]
    def yaw(elf, axis, angle):
        delta = step(elf, 0x16871c) if axis > 90 else (step(elf, 0x168cac) if axis < -90 else 0)
        value = f32(angle+delta)
        if value > pi:value = f32(value-two_pi)
        if value < -pi:value = f32(value+two_pi)
        return value
    yaw_cases = 0
    for axis in range(-128, 128):
        for angle in (-pi, -pi+.01, -1., 0., 1., pi-.01, pi):
            before, after = yaw(current, axis, angle), yaw(modified, axis, angle)
            circular_sum = (before+after-2*angle+two_pi/2) % two_pi - two_pi/2
            if abs(circular_sum) > 2e-6:
                raise ValueError('Yaw direction/angle-wrap fixture failed')
            if -90 <= axis <= 90 and before != after:
                raise ValueError('Yaw deadzone changed')
            yaw_cases += 1
    old_focal = struct.unpack('<f', struct.pack('<I', (word(current, 0x16aa5c) & 65535) << 16))[0]
    new_focal = struct.unpack('<f', struct.pack('<I', (word(modified, 0x16aa5c) & 65535) << 16))[0]
    def projection(elf):
        bits = (word(elf, 0x16aa74) & 65535) << 16 | word(elf, 0x16aa78) & 65535
        return struct.unpack('<f', struct.pack('<I', bits))[0]
    if new_focal / old_focal != .75 or not math.isclose(old_focal*projection(current), new_focal*projection(modified), rel_tol=1e-6, abs_tol=1e-6):
        raise ValueError('Widescreen projection coefficient fixture failed')
    return {'combinations': 16, 'yaw_axis_angle_cases': yaw_cases, 'store_cases': store_cases,
            'focal_scale': [old_focal, new_focal], 'localized_crc': pcsx2_crc(current),
            'rollback': 'all 16 combinations restored localized ELF byte-identically',
            'in_game_acceptance': 'user-operated; not executed by this tool'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--original', required=True, type=Path)
    p.add_argument('--iso', required=True, type=Path)
    p.add_argument('--manifest', required=True, type=Path)
    a = p.parse_args()
    original = verify_original(a.original, load_version(ROOT / 'assets/game-version.json'))
    manifest = json.loads(a.manifest.read_text('utf8'))
    if sha256_file(a.iso) != manifest['modified']['sha256']:
        raise ValueError('Runtime fixture ISO identity mismatch')
    runtime = manifest['full_text']['runtime_patches']['report']
    result = verify_fixtures(original.read(runtime['recipe']['resource']), IsoImage(a.iso).read(runtime['recipe']['resource']), runtime['recipe'])
    print('RUNTIME_FIXTURES PASS ' + json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
