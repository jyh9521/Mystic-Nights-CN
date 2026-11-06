"""Audit the retail caption scaffold and optionally build an offline ELF prototype.

This command never starts the game, installs files, or modifies an ISO. An empty
catalogue is an inventory, not a claim that spoken scenes have subtitles.
"""
import argparse
import json
from pathlib import Path
import shlex

from _bootstrap import ROOT
from mysticnights.cutscene_subtitles import (
    ORIGINAL_ISO_SHA256, build_engine_patch, build_script_edits, inspect_engine,
    inventory, replay_engine_hook, reverse_engine_patch, sha,
)
from mysticnights.font import encode_text
from mysticnights.iso9660 import IsoImage, sha256_file
from mysticnights.resources import parse_res
from mysticnights.versions import load_version, verify_original


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', 'utf8')
    assert json.loads(path.read_text('utf8')) == data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iso', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--localized', type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--catalogue', type=Path, help='All 47 identities; every nonempty cue must be audio-reviewed')
    parser.add_argument('--locale', default='zh-CN')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output directory must not exist')
    if bool(args.localized) != bool(args.manifest):
        parser.error('--localized and --manifest are required together')
    if args.catalogue and not args.localized:
        parser.error('--catalogue requires the explicit localized ISO and manifest')
    image = verify_original(args.iso, load_version(ROOT / 'assets/game-version.json'))
    original = image.read('SCKA_200.55'); engine = inspect_engine(original); scenes = inventory(image)
    catalogue = {'format': 'cutscene-subtitle-catalogue', 'version': 1, 'locale': args.locale,
                 'source_iso_sha256': ORIGINAL_ISO_SHA256,
                 'status': 'inventory-untranscribed', 'all_speech_transcribed': False,
                 'resources': [{**row, 'cues': []} for row in scenes]}
    args.output.mkdir(parents=True)
    save(args.output / 'engine-audit.json', engine)
    save(args.output / 'scene-inventory.json', scenes)
    save(args.output / 'catalogue-template.json', catalogue)
    print('CUTSCENE BASELINE PASS scenes=47 native_caption_nodes=0 caption_dispatch=no-op')
    if not args.localized:
        return
    manifest = json.loads(args.manifest.read_text('utf8'))
    if manifest['original']['sha256'] != ORIGINAL_ISO_SHA256 or manifest['modified']['sha256'] != sha256_file(args.localized):
        raise ValueError('Localized ISO and build manifest identity mismatch')
    localized_image = IsoImage(args.localized); current = localized_image.read('SCKA_200.55')
    mapping = manifest['font']['mapping']
    modified, receipt = build_engine_patch(original, current, manifest['entries'], mapping)
    if reverse_engine_patch(modified, receipt) != current:
        raise AssertionError('Subtitle prototype rollback is not byte-exact')
    code_output = args.output / 'MODIFIED_FILE.elf'; code_output.write_bytes(modified)
    save(args.output / 'DIFF_FILE.json', receipt)
    # Synthetic text is explicitly a code fixture, not substituted game dialogue.
    sample_text = next(row['target'] for row in manifest['entries'] if row.get('text_type') == 'dialogue' and row.get('target')) + '100%'
    test_text = encode_text(sample_text, mapping)
    nodes = [{'type': 0, 'index': 0, 'frame': 0}, {'type': 1, 'index': 0, 'frame': 720},
             {'type': 2, 'index': 0, 'frame': 720}]
    values = [{'end_frame_inclusive': 979, 'text': test_text}]
    results = []
    for frame, skip, expected in [(0, False, 0), (720, False, 0), (721, False, 2),
                                  (980, False, 2), (981, False, 0), (721, True, 0)]:
        row = replay_engine_hook(modified, receipt, frame=frame, nodes=nodes, captions=values, skip=skip)
        if len(row['draws']) != expected:
            raise AssertionError('Actual generated prototype frame replay mismatch')
        results.append({'frame': frame, 'skip': skip, **row})
    # Independent copies model clear/another scene: no global active caption persists.
    for frame in [0, 721]:
        row = replay_engine_hook(modified, receipt, frame=frame, nodes=[], captions=[])
        if row['draws']:
            raise AssertionError('Subtitle leaked into an empty/cleared scene')
        results.append({'frame': frame, 'state': 'cleared/empty', **row})
    save(args.output / 'prototype-replay.json', results)
    real_script_report = None
    if args.catalogue:
        requested = json.loads(args.catalogue.read_text('utf8'))
        edits, real_script_report = build_script_edits(image, requested, mapping)
        members = args.output / 'caption-members'; members.mkdir()
        for resource, changes in edits.items():
            archive = parse_res(image.read(resource))
            for key, data in changes.items():
                member = next(member for member in archive.entries if member.key == key)
                name = resource.replace('/', '__') + '__' + member.name
                (members / name).write_bytes(data)
        save(args.output / 'script-edits.json', real_script_report)
    # An actual source C005 timeline is exercised with an explicit synthetic cue,
    # preserving each original SOUND/OBJECT/FADE token and same-frame ordering.
    from mysticnights.cutscene_subtitles import inject_script
    c005 = next(row for row in scenes if row['scene'] == 'C005')
    source_script = parse_res(image.read(c005['resource'])).read(c005['member'])
    replacement, script_fixture = inject_script(source_script, [{
        'id': 'synthetic-c005-fixture', 'start_frame': 720, 'end_frame_exclusive': 980,
        'text': sample_text, 'status': 'reviewed',
        'source_audio_sha256': '0' * 64, 'source_transcript': 'synthetic offline fixture, not a game transcript',
    }], lambda text: encode_text(text, mapping), camera_frames=c005['camera_frames'])
    if len(replacement) != len(source_script):
        raise AssertionError('Actual C005 synthetic caption fixture resized the script')
    save(args.output / 'script-fixture.json', script_fixture)
    (args.output / 'C005-synthetic-fixture.SCR').write_bytes(replacement)
    root_script = (ROOT / 'tools/rollback_cutscene_subtitles.py').as_posix()
    shell = ('#!/usr/bin/env bash\nset -euo pipefail\n'
             'HERE="$(cd -- "$(dirname -- "$0")" && pwd)"\n'
             'test "$#" -eq 2 || { printf "%s\\n" "Usage: ROLLBACK.sh MODIFIED_ELF OUTPUT_ELF" >&2; exit 2; }\n'
             'python -B -X utf8 ' + shlex.quote(root_script) + ' --input "$1" --patch "$HERE/DIFF_FILE.json" --output "$2"\n')
    rollback = args.output / 'ROLLBACK.sh'; rollback.write_text(shell, 'utf8', newline='\n'); rollback.chmod(0o755)
    text = [
        'CUTSCENE ENGINE PROTOTYPE — offline, not installed',
        'CHANGED_BRANCH_FIELD: cutscene renderer / frame-driven captions prototype',
        'ORIGINAL_ISO_SHA256: ' + ORIGINAL_ISO_SHA256,
        'RETAIL_ELF_SHA256: ' + sha(original), 'LOCALIZED_ELF_BEFORE_SHA256: ' + sha(current),
        'MODIFIED_ELF_SHA256: ' + sha(modified),
        'MODIFIED_FILE: ' + str(code_output.resolve()),
        'DIFF_FILE: ' + str((args.output / 'DIFF_FILE.json').resolve()),
        'VERIFICATION: ' + str((args.output / 'VERIFICATION.txt').resolve()),
        'ROLLBACK: ' + str(rollback.resolve()),
        'BASELINE: 47 source cutscene scripts; zero CAPTION nodes; original type2 dispatch is no-op.',
        'MODIFIED: 8 actual generated-code frame/skip/clear fixtures passed; 128-bit callee saves and FontEnv restored; original Flip called exactly once.',
        'ROLLBACK: in-memory reverse bytes equal the full localized ELF before code patch.',
        'SCRIPT: actual C005 synthetic cue preserves all original semantic tokens and exact member length; not a real transcript.',
        'TRANSCRIPT: reviewed status, source audio SHA and source transcript are mandatory; ASR drafts are rejected.',
        'CONTENT_INSTALLED: none. No ISO, actual PCSX2 files or game process were modified/launched.',
        'EXTERNAL_TEXT_AND_FLIP_CALLS: contract stubs during instruction replay; no real GS rendering.',
        'SCRIPT_CATALOGUE: ' + ('explicit reviewed input supplied' if args.catalogue else 'none; template is untranscribed inventory'),
    ]
    verification = args.output / 'VERIFICATION.txt'; verification.write_text('\n'.join(text) + '\n', 'utf8')
    assert sha(code_output.read_bytes()) == sha(modified)
    assert json.loads((args.output / 'DIFF_FILE.json').read_text('utf8')) == receipt
    assert rollback.read_text('utf8') == shell and verification.read_text('utf8') == '\n'.join(text) + '\n'
    print('CUTSCENE PROTOTYPE PASS code_chunks=' + str(len(receipt['padding_owners'])) +
          ' code_and_hook_bytes=' + str(sum(len(bytes.fromhex(row['after'])) for row in receipt['writes'])) +
          ' replay_cases=8 same_length_SCR=pass rollback=localized-ELF-exact transcripts=not-installed game_executed=false')


if __name__ == '__main__':
    main()
