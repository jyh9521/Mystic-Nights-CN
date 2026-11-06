"""Build a local listening-review page without changing subtitle approval state.

The exported JSON keeps the complete source-bound subtitle catalogue, including
empty unapproved scenes. Audio paths live only in the generated page metadata.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import quote

from _bootstrap import ROOT


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def build(catalogue_path: Path, audio_manifest_path: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError(f'Use a new review HTML file: {output}')
    catalogue = json.loads(catalogue_path.read_text('utf8'))
    audio = json.loads(audio_manifest_path.read_text('utf8'))
    version = json.loads((ROOT / 'assets/game-version.json').read_text('utf8'))
    if (catalogue.get('format') != 'cutscene-subtitle-catalogue' or catalogue.get('version') != 1
            or catalogue.get('source_iso_sha256') != version['iso']['sha256']):
        raise ValueError('Unsupported/source-mismatched subtitle catalogue')
    if (audio.get('format') != 'cutscene-audio-survey' or audio.get('version') != 1
            or audio.get('source_iso_sha256') != catalogue['source_iso_sha256']):
        raise ValueError('Audio survey and subtitle source identities differ')
    resources = catalogue.get('resources')
    if not isinstance(resources, list) or len(resources) != 47:
        raise ValueError('Review must retain the complete 47-scene catalogue')
    scenes = set()
    cue_ids = set()
    audio_by_id = {}
    for row in audio['audio']:
        if row['id'] in audio_by_id:
            raise ValueError('Duplicate audio survey ID')
        audio_by_id[row['id']] = row
    audio_map = {}
    base = audio_manifest_path.resolve().parent
    for resource in resources:
        if resource['scene'] in scenes or not isinstance(resource.get('cues'), list):
            raise ValueError('Duplicate scene or malformed cues')
        scenes.add(resource['scene'])
        for cue in resource['cues']:
            if cue['id'] in cue_ids:
                raise ValueError('Duplicate subtitle cue ID')
            cue_ids.add(cue['id'])
            row = audio_by_id.get(cue['source_audio_id'])
            if row is None or row['source_sha256'] != cue['source_audio_sha256']:
                raise ValueError(f'Subtitle/audio source mismatch: {cue["id"]}')
            if cue.get('wav', {}).get('sha256') != row['wav']['sha256']:
                raise ValueError(f'Subtitle/WAV source mismatch: {cue["id"]}')
            path = (base / row['wav']['path']).resolve()
            if not path.is_relative_to(base) or not path.is_file():
                raise ValueError('Audio path escaped its extraction directory')
            if path.stat().st_size != row['wav']['size'] or sha(path) != row['wav']['sha256']:
                raise ValueError('Review audio changed after extraction')
            relative = os.path.relpath(path, output.resolve().parent).replace('\\', '/')
            audio_map[row['id']] = {'path': quote(relative, safe='/.'),
                                   'source_sha256': row['source_sha256'],
                                   'wav_sha256': row['wav']['sha256']}
    meta = {'catalogue_sha256': sha(catalogue_path), 'audio_manifest_sha256': sha(audio_manifest_path),
            'audio_map': audio_map}
    template = (ROOT / 'tools/review_page/cutscene_audio.html').read_text('utf8')
    if template.count('CATALOGUE_JSON_PLACEHOLDER') != 1 or template.count('AUDIO_META_JSON_PLACEHOLDER') != 1:
        raise ValueError('Review template placeholder mismatch')
    encode = lambda data: json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    html = template.replace('CATALOGUE_JSON_PLACEHOLDER', encode(catalogue)).replace('AUDIO_META_JSON_PLACEHOLDER', encode(meta))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf8', newline='\n') as stream:
        stream.write(html)
    assert output.read_text('utf8') == html
    return {'scenes': len(resources), 'cues': len(cue_ids), 'mapped_audio': len(audio_map),
            'empty_scenes_unchanged': sum(not r['cues'] for r in resources),
            'auto_approved': 0, 'sha256': sha(output)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalogue', type=Path, required=True)
    parser.add_argument('--audio-manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.catalogue, args.audio_manifest, args.output), ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
