"""Build an entirely offline, final-ISO-backed side-by-side feedback webpage."""
import argparse
import json
from pathlib import Path
from _bootstrap import ROOT
from mysticnights.image_review import build_review


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--original', type=Path, required=True)
    p.add_argument('--iso', type=Path, required=True)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--locale', default='zh-CN')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--audit', type=Path)
    p.add_argument('--feedback', type=Path, help='Optional local previous feedback; never published to Git')
    a = p.parse_args()
    print(json.dumps(build_review(ROOT, a.original, a.iso, a.manifest, a.locale, a.output,
                                 audit_path=a.audit, feedback_path=a.feedback), ensure_ascii=False))


if __name__ == '__main__':
    main()
