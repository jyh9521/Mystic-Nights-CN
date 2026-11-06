"""Extract source-bound cutscene sound schedules and optionally decode review WAVs.

Reads only a verified original disc; output must be a new directory.  No game or
emulator is started.  FFmpeg is an explicit caller-supplied optional decoder.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import wave

from _bootstrap import ROOT
from mysticnights.cutscene_audio import (
    cutscene_sound_commands, make_vag, parse_mih, parse_vag, split_mib,
)
from mysticnights.resources import parse_res
from mysticnights.versions import load_version, verify_original


def digest(data):
    return hashlib.sha256(data).hexdigest()


def extract(image, output: Path, ffmpeg: Path | None = None) -> dict:
    if output.exists():
        raise FileExistsError(f'Use a new output directory: {output}')
    if ffmpeg is not None and not ffmpeg.is_file():
        raise FileNotFoundError(ffmpeg)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.' + output.name + '-', dir=output.parent) as temp:
        work = Path(temp)
        (work / 'raw').mkdir()
        (work / 'wav').mkdir()
        archives = {}
        scenes = []
        pending = {}
        for path in sorted(image.files):
            if not path.startswith('RES/CUTSCENE/') or not path.endswith('.RES'):
                continue
            archives[path] = parse_res(image.read(path))
        # The cutscene script can also select ordinary resident effects.  Keep
        # this source explicit instead of inventing a same-scene filename.
        archives['RES/SYSTEM.RES'] = parse_res(image.read('RES/SYSTEM.RES'))
        for path, archive in archives.items():
            for member in archive.entries:
                if not re.fullmatch(r'C\d{3}\.SCR', member.name):
                    continue
                data = archive.read(member)
                scene = {'id': member.name[:-4], 'resource': path, 'member': member.name,
                         'member_offset': member.offset, 'member_size': member.size,
                         'source_sha256': digest(data), 'sounds': cutscene_sound_commands(data),
                         'caption_blocks': len(re.findall(rb'\bCAPTION\s*\{', data))}
                for sound in scene['sounds']:
                    name = sound['name'].replace('\\', '/')
                    if sound['sound_type'] == 'BGM':
                        src = 'RES/SOUND/BGM/' + name
                        key = 'mib:' + src + '.MIB'
                        pending[key] = {'kind': 'mih-mib', 'resource': src + '.MIB',
                                        'header_resource': src + '.MIH'}
                    elif sound['sound_type'] == 'VOICE':
                        src = 'RES/SOUND/VOICE/' + name
                        key = 'vag:' + src
                        pending[key] = {'kind': 'vag', 'resource': src}
                    else:
                        candidates = []
                        for other_path, other in archives.items():
                            if Path(other_path).stem.split('_')[0] != scene['id']:
                                continue
                            for entry in other.entries:
                                if entry.name == name:
                                    candidates.append((other_path, entry, other.read(entry)))
                        if not candidates:
                            common = archives['RES/SYSTEM.RES']
                            candidates = [('RES/SYSTEM.RES', e, common.read(e))
                                          for e in common.entries if e.name == name]
                        if not candidates or len({digest(c[2]) for c in candidates}) != 1:
                            raise ValueError(f'Missing/ambiguous effect {scene["id"]}:{name}')
                        src, entry, _ = candidates[0]
                        key = f'res-vag:{src}:{entry.group}:{entry.index}'
                        pending[key] = {'kind': 'res-vag', 'resource': src,
                                        'member': entry.name, 'group': entry.group, 'index': entry.index,
                                        'member_offset': entry.offset, 'member_size': entry.size}
                    sound['audio_id'] = key
                scenes.append(scene)

        audio = []
        commands = []
        version_output = None
        if ffmpeg:
            version_output = subprocess.check_output([str(ffmpeg), '-version'], encoding='utf8').splitlines()[0]
        for index, (key, row) in enumerate(sorted(pending.items()), 1):
            row = {'id': key, **row}
            stem = f'{index:03d}-' + Path(row.get('member', row['resource'])).stem
            if row['kind'] == 'mih-mib':
                body = image.read(row['resource'])
                header = image.read(row['header_resource'])
                info = parse_mih(header)
                row.update({'source_sha256': digest(body), 'source_bytes': len(body),
                            'header_sha256': digest(header), 'profile': asdict(info),
                            'samples': info.samples, 'channels': info.channels})
                channel_data = split_mib(info, body)
                (work / 'raw' / (stem + '.MIH')).write_bytes(header)
                (work / 'raw' / (stem + '.MIB')).write_bytes(body)
                decode_inputs = []
                for ch, payload in enumerate(channel_data):
                    filename = f'{stem}-channel{ch + 1}.VAG'
                    data = make_vag(payload, info.sample_rate, f'channel{ch + 1}')
                    (work / 'raw' / filename).write_bytes(data)
                    decode_inputs.append(work / 'raw' / filename)
            else:
                if row['kind'] == 'vag':
                    data = image.read(row['resource'])
                else:
                    archive = archives[row['resource']]
                    entry = next(e for e in archive.entries if e.key == (row['group'], row['index']))
                    data = archive.read(entry)
                info = parse_vag(data)
                row.update({'source_sha256': digest(data), 'source_bytes': len(data),
                            'profile': asdict(info), 'samples': info.samples, 'channels': 1})
                target = work / 'raw' / (stem + '.VAG')
                target.write_bytes(data)
                decode_inputs = [target]
            row['duration_samples'] = {'numerator': row['samples'], 'denominator': info.sample_rate}
            row['duration_seconds'] = row['samples'] / info.sample_rate
            if ffmpeg:
                target = work / 'wav' / (stem + '.wav')
                argv = [str(ffmpeg), '-hide_banner', '-nostdin', '-loglevel', 'error']
                for p in decode_inputs:
                    argv += ['-i', str(p.relative_to(work))]
                if len(decode_inputs) > 1:
                    argv += ['-filter_complex', f'amerge=inputs={len(decode_inputs)}']
                argv += ['-c:a', 'pcm_s16le', '-bitexact', str(target.relative_to(work))]
                result = subprocess.run(argv, cwd=work, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf8', errors='replace')
                commands.append({'argv': argv, 'output': result.stdout, 'exit_status': result.returncode})
                if result.returncode:
                    raise ValueError(f'Decoder failed: {result.stdout}')
                with wave.open(str(target), 'rb') as wav:
                    if (wav.getnchannels(), wav.getframerate(), wav.getnframes(), wav.getsampwidth()) != (row['channels'], info.sample_rate, row['samples'], 2):
                        raise ValueError(f'Decoder output profile mismatch: {row["id"]}')
                row['wav'] = {'path': 'wav/' + target.name, 'size': target.stat().st_size,
                              'sha256': digest(target.read_bytes())}
            audio.append(row)
        summary = {'scenes': len(scenes), 'sound_commands': sum(len(s['sounds']) for s in scenes),
                   'explicit_voice_commands': sum(c['sound_type'] == 'VOICE' for s in scenes for c in s['sounds']),
                   'source_caption_blocks': sum(s['caption_blocks'] for s in scenes),
                   'unique_audio_inputs': len(audio), 'decoded_wavs': sum('wav' in a for a in audio),
                   'frame_units': 'original engine frame; no wall-clock or FPS assumption',
                   'speech_review': 'not performed by extraction; no inferred subtitles'}
        with image.path.open('rb') as stream:
            iso_digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        manifest = {'format': 'cutscene-audio-survey', 'version': 1,
                    'source_iso_sha256': iso_digest,
                    'decoder': version_output, 'summary': summary, 'scenes': scenes, 'audio': audio,
                    'decoder_commands': commands}
        (work / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', 'utf8')
        assert json.loads((work / 'manifest.json').read_text('utf8')) == manifest
        for row in audio:
            if 'wav' in row:
                p = work / row['wav']['path']
                assert digest(p.read_bytes()) == row['wav']['sha256']
        if output.exists():
            raise FileExistsError(output)
        work.rename(output)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iso', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--ffmpeg', type=Path, help='Explicit existing FFmpeg executable for review WAVs')
    args = parser.parse_args()
    image = verify_original(args.iso, load_version(ROOT / 'assets/game-version.json'))
    print(json.dumps(extract(image, args.output, args.ffmpeg), ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
