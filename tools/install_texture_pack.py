#!/usr/bin/env python3
"""Explicitly install or roll back a generated texture pack; never launch PCSX2."""
import argparse
import json
from pathlib import Path

from _bootstrap import ROOT
from mysticnights.texture_install import install_package,rollback_install


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',type=Path)
    parser.add_argument('--data-dir',type=Path)
    parser.add_argument('--receipt',required=True,type=Path)
    parser.add_argument('--rollback',action='store_true')
    args=parser.parse_args()
    if args.rollback:
        if args.package or args.data_dir:
            parser.error('Rollback takes only --receipt')
        report=rollback_install(args.receipt); verb='ROLLBACK'
    else:
        if not args.package or not args.data_dir:
            parser.error('Install requires --package and --data-dir')
        report=install_package(args.package,args.data_dir,args.receipt); verb='INSTALL'
    print(f"TEXTURE {verb} PASS files={len(report['files'])} serial={report['serial']} state={report['state']} emulator=not-launched")
    print(json.dumps({'profile':report['profile'],'textures_directory':report['textures_directory'],
                      'files':[row['target'] for row in report['files']],
                      'receipt':str(args.receipt.resolve())},ensure_ascii=False))


if __name__=='__main__': main()
