"""Reverse only an explicitly source-bound cutscene renderer ELF prototype."""
import argparse
import json
from pathlib import Path

from _bootstrap import ROOT
from mysticnights.cutscene_subtitles import reverse_engine_patch, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--patch', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists() or args.output.resolve() == args.input.resolve():
        parser.error('Rollback output must be a new file')
    source = args.input.read_bytes(); receipt = json.loads(args.patch.read_text('utf8'))
    restored = reverse_engine_patch(source, receipt)
    with args.output.open('xb') as stream:
        stream.write(restored)
    if args.output.read_bytes() != restored:
        raise AssertionError('Caption rollback output readback mismatch')
    print('CUTSCENE ROLLBACK PASS bytes=' + str(len(restored)) + ' sha256=' + sha(restored) + ' restored=localized-ELF-before-subtitle-hook')


if __name__ == '__main__':
    main()
