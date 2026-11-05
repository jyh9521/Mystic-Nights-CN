"""Install or roll back generated PNACH files without launching PCSX2/game."""
import argparse
import json
from pathlib import Path
from _bootstrap import ROOT
from mysticnights.runtime_install import install_package, rollback_install


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',type=Path)
    parser.add_argument('--data-dir',type=Path)
    parser.add_argument('--receipt',required=True,type=Path)
    parser.add_argument('--role',choices=('localized','original'),default='localized')
    parser.add_argument('--enable-patch',action='append',default=[])
    parser.add_argument('--allow-cheats',action='store_true')
    parser.add_argument('--settings-from',type=Path,help='Copy existing same-serial per-game INI verbatim to the new CRC')
    parser.add_argument('--rollback',action='store_true')
    args=parser.parse_args()
    if args.rollback:
        if args.package or args.data_dir or args.enable_patch or args.allow_cheats or args.settings_from:
            parser.error('Rollback takes only --receipt')
        report=rollback_install(args.receipt);verb='ROLLBACK'
    else:
        if not args.package or not args.data_dir:parser.error('Install requires --package and --data-dir')
        report=install_package(args.package,args.data_dir,args.receipt,role=args.role,
                               enabled_patches=args.enable_patch,allow_cheats=args.allow_cheats,
                               settings_from=args.settings_from)
        verb='INSTALL'
    print('RUNTIME '+verb+' PASS files='+str(len(report['files']))+' crc='+report['stem'].rsplit('_',1)[1]+' state='+report['state'])
    print(json.dumps({'profile':report['profile'],'files':[r['target'] for r in report['files']],
                      'enabled_patches':report['enabled_patches'],'cheat_master':report['cheat_master'],
                      'enabled_cheat_groups':report['enabled_cheat_groups']},ensure_ascii=False))


if __name__=='__main__':main()
