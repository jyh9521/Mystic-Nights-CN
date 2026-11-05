"""Validate returned image opinions and emit a resource/hash-bound worklist."""
import argparse
import json
from pathlib import Path
from _bootstrap import ROOT
from mysticnights.image_review import read_feedback, canonical


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--feedback', type=Path, required=True)
    p.add_argument('--review-manifest', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise ValueError('Output exists; do not replace earlier feedback')
    result = read_feedback(a.feedback, json.loads(a.review_manifest.read_text('utf8')))
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_bytes(canonical(result))
    assert json.loads(a.output.read_text('utf8')) == result
    print(f'FEEDBACK PASS entries={len(result["entries"])} opinions={result["opinion_entries"]} stale={sum(r["stale"] for r in result["entries"])} output={a.output.resolve()}')


if __name__ == '__main__':
    main()
