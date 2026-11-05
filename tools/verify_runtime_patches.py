"""Offline instruction fixtures; never opens an emulator or attaches to a game."""
import argparse
import itertools
import json
import math
import struct
from pathlib import Path
from functools import lru_cache
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


@lru_cache(maxsize=4)
def _vertical_program(elf):
    return {address: word(elf, address)
            for start, stop in ((0x16a2c4, 0x16a318), (0x16a744, 0x16a778))
            for address in range(start, stop, 4)}


def replay_vertical_input(elf, axis, height, *, upper, lower, inhibited=False):
    """Replay only the actual scalar vertical-input/clamp blocks, including delays.

    This stops before the subsequent camera/collision calculations. FPU
    accumulator/MMI instructions and the rest of UpdateCamera are not emulated.
    The positive branch's conditional upper clamp and its pre-existing inhibit
    gate are deliberately preserved, rather than replaced by a generic clamp.
    """
    if not -32768 <= axis <= 32767:
        raise ValueError('Vertical fixture axis is outside signed halfword range')
    program = _vertical_program(elf)
    registers = [0] * 32; fp = [0.] * 32
    player, camera = 0x10000, 0x20000
    registers[2] = player; registers[6] = int(inhibited); registers[16] = camera
    fp[4] = struct.unpack('<f', struct.pack('<f', upper))[0]
    memory = {player+0x860: axis, camera+0x208: height, camera+0x214: lower}
    pc, pending, condition = 0x16a2c4, None, False
    def signed(value):return value if value < 0x80000000 else value-0x100000000
    def f32(value):return struct.unpack('<f', struct.pack('<f', value))[0]
    for _ in range(128):
        if pc == 0x16a318:
            return f32(memory[camera+0x208])
        if pc not in program:
            raise ValueError('Vertical fixture escaped verified instruction blocks')
        instruction = program[pc]
        op, rs, rt = instruction >> 26, instruction >> 21 & 31, instruction >> 16 & 31
        immediate = instruction & 65535
        displacement = immediate if immediate < 32768 else immediate-65536
        target = None
        if instruction == 0:
            pass
        elif op == 0 and instruction & 63 == 0x23:
            rd = instruction >> 11 & 31
            registers[rd] = (registers[rs]-registers[rt]) & 0xffffffff
        elif op == 0x21:  # LH
            registers[rt] = memory[registers[rs]+displacement] & 0xffffffff
        elif op == 0x0a:  # SLTI
            registers[rt] = int(signed(registers[rs]) < displacement)
        elif op in (4, 5):
            if (registers[rs] == registers[rt]) == (op == 4):
                target = pc+4+displacement*4
        elif op == 0x0f:
            registers[rt] = immediate << 16
        elif op == 0x31:  # LWC1
            fp[rt] = f32(memory[registers[rs]+displacement])
        elif op == 0x39:  # SWC1
            memory[registers[rs]+displacement] = f32(fp[rt])
        elif op == 0x11:
            fs, fd, fn = instruction >> 11 & 31, instruction >> 6 & 31, instruction & 63
            if rs == 4:  # MTC1, rt is the GPR and fs is the FPR
                fp[fs] = struct.unpack('<f', struct.pack('<I', registers[rt]))[0]
            elif rs == 8:  # BC1F / BC1T
                if rt not in (0, 1):raise ValueError('Unexpected vertical COP1 branch')
                if condition == bool(rt):target = pc+4+displacement*4
            elif rs == 16 and fn in (0, 1):
                fp[fd] = f32(fp[fs]+fp[rt] if fn == 0 else fp[fs]-fp[rt])
            elif rs == 16 and fn in (0x34, 0x36):
                condition = fp[fs] < fp[rt] if fn == 0x34 else fp[fs] <= fp[rt]
            else:raise ValueError('Unsupported vertical FPU fixture instruction')
        else:
            raise ValueError(f'Unsupported vertical fixture instruction {instruction:08X}')
        registers[0] = 0
        old_pending, pending = pending, target
        pc = old_pending if old_pending is not None else pc+4
    raise ValueError('Vertical instruction fixture budget exceeded')


def verify_fixtures(original, current, recipe):
    validate_recipe(original, current, recipe)
    if _vertical_program(original) != _vertical_program(current):
        raise ValueError('Localized vertical camera instruction blocks changed before optional patches')
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
    # Input negation (not signed step replacement) routes through the original
    # gate and clamp bodies. Check the exact scalar blocks and branch delays.
    vertical_cases = 0
    for lower, upper in ((-10., 0.), (-5., -1.), (-1., 2.)):
        heights = (lower-.5, lower, lower+.25, (lower+upper)/2, upper-.25, upper, upper+.5)
        for inhibited in (False, True):
            for axis in range(-128, 128):
                for height in heights:
                    expected = replay_vertical_input(current, -axis, height, upper=upper, lower=lower, inhibited=inhibited)
                    after = replay_vertical_input(modified, axis, height, upper=upper, lower=lower, inhibited=inhibited)
                    if expected != after:
                        raise ValueError('Vertical input/clamp/inhibit instruction fixture failed')
                    if -90 <= axis <= 90:
                        before = replay_vertical_input(current, axis, height, upper=upper, lower=lower, inhibited=inhibited)
                        if before != after:raise ValueError('Vertical deadzone changed')
                    vertical_cases += 1
    old_focal = struct.unpack('<f', struct.pack('<I', (word(current, 0x16aa5c) & 65535) << 16))[0]
    new_focal = struct.unpack('<f', struct.pack('<I', (word(modified, 0x16aa5c) & 65535) << 16))[0]
    def projection(elf):
        bits = (word(elf, 0x16aa74) & 65535) << 16 | word(elf, 0x16aa78) & 65535
        return struct.unpack('<f', struct.pack('<I', bits))[0]
    if new_focal / old_focal != .75 or not math.isclose(old_focal*projection(current), new_focal*projection(modified), rel_tol=1e-6, abs_tol=1e-6):
        raise ValueError('Widescreen projection coefficient fixture failed')
    return {'combinations': 16, 'yaw_axis_angle_cases': yaw_cases, 'vertical_axis_height_cases': vertical_cases,
            'vertical_clamp_gate': 'original branches preserved under input negation', 'store_cases': store_cases,
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
