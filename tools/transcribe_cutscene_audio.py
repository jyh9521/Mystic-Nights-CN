"""Create explicitly unreviewed ASR evidence from source-checked review WAVs.

Requires an already installed faster-whisper and an explicit local model
directory.  This command never downloads a model, edits a subtitle catalogue,
marks a transcript reviewed, or starts the game.
"""
import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import tempfile

from _bootstrap import ROOT


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def checked_inputs(manifest_path: Path, selection: str):
    if selection not in {'voice', 'scene', 'all'}:
        raise ValueError('Unsupported audio selection')
    manifest = json.loads(manifest_path.read_text('utf8'))
    original = json.loads((ROOT / 'assets/game-version.json').read_text('utf8'))
    if (manifest.get('format') != 'cutscene-audio-survey' or manifest.get('version') != 1
            or manifest.get('source_iso_sha256') != original['iso']['sha256']):
        raise ValueError('A supported original-disc cutscene-audio-survey is required')
    base = manifest_path.resolve().parent
    selected = []
    seen = set()
    for row in manifest['audio']:
        if row['id'] in seen:
            raise ValueError('Duplicate source audio ID')
        seen.add(row['id'])
        keep = (selection == 'all' or row['kind'] == 'vag'
                or selection == 'scene' and row['kind'] == 'mih-mib'
                and Path(row['resource']).stem.startswith('C'))
        if not keep:
            continue
        path = (base / row['wav']['path']).resolve()
        if not path.is_relative_to(base) or not path.is_file() or path.is_symlink():
            raise ValueError('Review WAV path escaped the extraction directory')
        if path.stat().st_size != row['wav']['size'] or sha(path) != row['wav']['sha256']:
            raise ValueError(f'Review WAV hash/size mismatch: {row["id"]}')
        selected.append((row, path))
    return manifest, selected


def transcribe(manifest_path, model_path, output, device='cpu', selection='scene'):
    if output.exists():
        raise FileExistsError(f'Use a new output directory: {output}')
    if not (model_path / 'model.bin').is_file():
        raise FileNotFoundError('An explicit existing CTranslate2 Whisper model directory is required')
    manifest, inputs = checked_inputs(manifest_path, selection)
    model_files = [{'path': p.name, 'size': p.stat().st_size, 'sha256': sha(p)}
                   for p in sorted(model_path.iterdir()) if p.is_file()]
    # Optional dependency: importing extraction tools or running core tests does
    # not import a speech runtime or require a model/network connection.
    from faster_whisper import WhisperModel
    compute = 'int8' if device == 'cpu' else 'float16'
    model = WhisperModel(str(model_path.resolve()), device=device, compute_type=compute,
                         cpu_threads=8, local_files_only=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.' + output.name + '-', dir=output.parent) as temporary:
        work = Path(temporary)
        records = []
        for index, (row, path) in enumerate(inputs, 1):
            segments, info = model.transcribe(
                str(path), language='ko', beam_size=5, temperature=0,
                condition_on_previous_text=False, vad_filter=True,
                vad_parameters={'min_silence_duration_ms': 400}, word_timestamps=True)
            data = {'status': 'asr-draft', 'human_listening_verified': False,
                    'audio_id': row['id'], 'source_sha256': row['source_sha256'],
                    'wav_sha256': row['wav']['sha256'], 'segments': []}
            for segment in segments:
                data['segments'].append({
                    'start': float(segment.start), 'end': float(segment.end),
                    'text': segment.text, 'avg_logprob': float(segment.avg_logprob),
                    'no_speech_prob': float(segment.no_speech_prob),
                    'compression_ratio': float(segment.compression_ratio),
                    'words': [{'word': w.word, 'start': float(w.start), 'end': float(w.end),
                               'probability': float(w.probability)} for w in segment.words or []]})
            filename = f'{index:03d}.json'
            target = work / filename
            target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', 'utf8')
            assert json.loads(target.read_text('utf8')) == data
            records.append({'path': filename, 'sha256': sha(target), 'audio_id': row['id']})
            print(row['id'] + ': ' + ' '.join(s['text'].strip() for s in data['segments']), flush=True)
        report = {'format': 'cutscene-asr-evidence', 'version': 1,
                  'status': 'asr-draft', 'human_listening_verified': False,
                  'source_iso_sha256': manifest['source_iso_sha256'],
                  'source_manifest_sha256': sha(manifest_path), 'selection': selection,
                  'device': device, 'compute_type': compute, 'model_files': model_files,
                  'runtime_versions': {n: version(n) for n in ['faster-whisper', 'ctranslate2']},
                  'language': 'ko', 'model_download': False, 'records': records,
                  'note': 'Music/effects can produce hallucinated text. VAD silence is not listening proof. No cue is approved or installed.'}
        (work / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', 'utf8')
        assert json.loads((work / 'manifest.json').read_text('utf8')) == report
        if output.exists():
            raise FileExistsError(output)
        work.rename(output)
    return len(records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--model-path', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    parser.add_argument('--selection', choices=['voice', 'scene', 'all'], default='scene')
    args = parser.parse_args()
    count = transcribe(args.manifest, args.model_path, args.output, args.device, args.selection)
    print(f'ASR DRAFTS PASS inputs={count} reviewed=0 installed=0')


if __name__ == '__main__':
    main()
