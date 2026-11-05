"""Explicit, reversible PNACH installation into an existing PCSX2 user profile.

No process is started. Global settings, BIOS and saves are never written.
Only selected PNACH files and, optionally, a new CRC-specific game INI are
managed. A receipt contains byte-verified backups for isolated rollback.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _plain_path(path):
    path = path.absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or getattr(part, 'is_junction', lambda: False)():
            raise ValueError('Runtime install path contains a link/junction')
    return path.resolve()


def profile_folders(directory):
    root = _plain_path(Path(directory))
    ini = root / 'inis/PCSX2.ini'
    if not root.is_dir() or not ini.is_file():
        raise ValueError('Expected an existing PCSX2 user profile with inis/PCSX2.ini')
    _plain_path(ini)
    values = {}; section = ''
    for line in ini.read_text('utf-8-sig').splitlines():
        line = line.strip()
        if line.startswith('[') and line.endswith(']'):
            section = line[1:-1].casefold()
        elif section == 'folders' and '=' in line and not line.startswith((';', '#')):
            key, value = [s.strip() for s in line.split('=', 1)]
            key = key.casefold()
            if key not in ('patches', 'cheats'):
                continue
            if key in values or not value or any(c in value for c in '\x00\r\n'):
                raise ValueError('Invalid/duplicate PCSX2 runtime folder')
            values[key] = value
    folders = {}
    for kind in ('patches', 'cheats'):
        value = values.get(kind, kind).replace('\\', os.sep)
        path = Path(value)
        folders[kind] = _plain_path(path if path.is_absolute() else root/path)
    folders['gamesettings'] = _plain_path(root/'gamesettings')
    if len(set(folders.values())) != 3:
        raise ValueError('Runtime folders overlap')
    return root, folders


def _atomic_write(path, data):
    fd, temporary = tempfile.mkstemp(prefix='.runtime-install-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _state(path):
    _plain_path(path)
    if path.exists() and not path.is_file():
        raise ValueError('Runtime target is not a regular file')
    return path.read_bytes() if path.exists() else None


def _save_receipt(directory, report):
    data = (json.dumps(report, ensure_ascii=False, indent=2)+'\n').encode('utf8')
    _atomic_write(directory/'receipt.json', data)
    if json.loads((directory/'receipt.json').read_text('utf8')) != report:
        raise ValueError('Runtime receipt readback mismatch')


def install_package(package, data_directory, receipt_directory, *, role='localized',
                    enabled_patches=(), allow_cheats=False, settings_from=None):
    package = _plain_path(Path(package)); receipt_directory = _plain_path(Path(receipt_directory))
    root, folders = profile_folders(data_directory)
    if role not in ('localized', 'original'):
        raise ValueError('Unknown runtime package role')
    if receipt_directory.exists():
        raise FileExistsError('Runtime receipt directory already exists')
    metadata = json.loads((package/'manifest.json').read_text('utf8'))
    if metadata.get('format') != 'runtime-patch-package' or metadata.get('version') != 1:
        raise ValueError('Unknown runtime package manifest')
    identities = [r for r in metadata['identities'] if r['role'] == role]
    if len(identities) != 1:
        raise ValueError('Runtime role identity missing/duplicate')
    stem = metadata['recipe']['serial']+'_'+identities[0]['crc']
    if not re.fullmatch(r'[A-Z]{4}-[0-9]{5}_[0-9A-F]{8}', stem):
        raise ValueError('Invalid runtime serial/CRC')
    entries = {r['path']: r for r in metadata['files']}
    if len(entries) != len(metadata['files']):
        raise ValueError('Duplicate runtime package path')
    plan = []; available_groups = {}
    for kind in ('patches', 'cheats'):
        name = f'{role}/{kind}/{stem}.pnach'
        if name not in entries:
            raise ValueError('Runtime package file missing')
        path = _plain_path(package/PurePosixPath(name))
        if not path.is_relative_to(package):
            raise ValueError('Runtime package escaped its root')
        data = path.read_bytes(); row = entries[name]
        if len(data) != row['size'] or _sha(data) != row['sha256']:
            raise ValueError('Runtime package integrity mismatch')
        groups = [s[1:-1] for s in data.decode('utf8').splitlines() if s.startswith('[') and s.endswith(']')]
        if not groups or len(groups) != len(set(groups)):
            raise ValueError('Runtime groups missing/duplicate')
        available_groups[kind] = set(groups)
        target = folders[kind]/(stem+'.pnach')
        plan.append((kind, target, data, _state(target)))
    enabled_patches = list(enabled_patches); enabled_cheats = []; settings_source = None
    if (len(enabled_patches) != len(set(enabled_patches)) or not set(enabled_patches) <= available_groups['patches']
            or any(any(c in p for c in '\r\n[]=') for p in enabled_patches)):
        raise ValueError('Unknown/invalid enabled patch group')
    if settings_from is not None:
        if enabled_patches or allow_cheats:
            raise ValueError('Settings migration and new preference flags are exclusive')
        source = _plain_path(Path(settings_from))
        serial = metadata['recipe']['serial']
        if (source.parent != folders['gamesettings'] or source.name == stem+'.ini'
                or not re.fullmatch(re.escape(serial)+r'_[0-9A-F]{8}\.ini', source.name)
                or not source.is_file()):
            raise ValueError('Settings migration requires another CRC of the same serial in this profile')
        source_data = source.read_bytes(); section = ''; allow_cheats = None
        selected = {'patches':enabled_patches, 'cheats':enabled_cheats}
        for line in source_data.decode('utf-8-sig').splitlines():
            line = line.strip()
            if line.startswith('[') and line.endswith(']'):
                section = line[1:-1].casefold()
            elif '=' in line and not line.startswith((';','#')):
                key, value = [p.strip() for p in line.split('=',1)]
                if section in selected and key.casefold() == 'enable':
                    if value not in available_groups[section] or value in selected[section]:
                        raise ValueError('Unknown/duplicate migrated settings group')
                    selected[section].append(value)
                elif section == 'emucore' and key.casefold() == 'enablecheats':
                    if value.casefold() not in ('true','false') or allow_cheats is not None:
                        raise ValueError('Invalid/duplicate migrated cheat master')
                    allow_cheats = value.casefold() == 'true'
        target = folders['gamesettings']/(stem+'.ini'); before = _state(target)
        if before is not None and before != source_data:
            raise FileExistsError('Existing per-game settings differ from migration source')
        plan.append(('gamesettings', target, source_data, before))
        settings_source = {'path':str(source), 'sha256':_sha(source_data)}
    elif enabled_patches or allow_cheats:
        text = '[EmuCore]\nEnableCheats = '+('true' if allow_cheats else 'false')+'\n\n[Patches]\n'
        text += ''.join('Enable = '+name+'\n' for name in enabled_patches)
        data = text.encode('utf8'); target = folders['gamesettings']/(stem+'.ini')
        before = _state(target)
        if before is not None and before != data:
            raise FileExistsError('Existing per-game settings differ; install PNACH only and select groups in PCSX2')
        plan.append(('gamesettings', target, data, before))
    receipt_directory.mkdir(parents=True)
    (receipt_directory/'before').mkdir()
    rows = []
    for index, (kind, target, data, before) in enumerate(plan):
        backup = None
        if before is not None:
            backup = f'before/{index}.bin'; (receipt_directory/backup).write_bytes(before)
            if (receipt_directory/backup).read_bytes() != before:
                raise ValueError('Runtime backup readback mismatch')
        rows.append({'kind':kind, 'target':str(target), 'after_sha256':_sha(data), 'after_size':len(data),
                     'before_sha256':None if before is None else _sha(before), 'backup':backup})
    report = {'format':'runtime-install-receipt', 'version':1, 'state':'prepared',
              'profile':str(root), 'folders':{k:str(v) for k,v in folders.items()}, 'role':role,
              'stem':stem, 'files':rows, 'enabled_patches':enabled_patches,
              'cheat_master':allow_cheats, 'enabled_cheat_groups':enabled_cheats,
              'settings_source':settings_source,
              'global_ini_sha256':_sha((root/'inis/PCSX2.ini').read_bytes())}
    _save_receipt(receipt_directory, report)
    committed = []
    try:
        if settings_source is not None and _sha(source.read_bytes()) != settings_source['sha256']:
            raise ValueError('Settings source changed during installation')
        for kind, target, data, before in plan:
            if _state(target) != before:
                raise ValueError('Runtime target changed during installation')
            target.parent.mkdir(parents=True, exist_ok=True)
            _plain_path(target.parent)
            _atomic_write(target, data); committed.append((target,before))
            if target.read_bytes() != data:
                raise ValueError('Installed runtime file readback mismatch')
        if _sha((root/'inis/PCSX2.ini').read_bytes()) != report['global_ini_sha256']:
            raise ValueError('Global INI changed during runtime installation')
        if settings_source is not None and _sha(source.read_bytes()) != settings_source['sha256']:
            raise ValueError('Settings source changed during installation')
    except BaseException:
        for target, before in reversed(committed):
            if before is None:target.unlink()
            else:_atomic_write(target,before)
        report['state']='aborted-restored';_save_receipt(receipt_directory,report)
        raise
    report['state']='installed';_save_receipt(receipt_directory,report)
    return report


def rollback_install(receipt_directory):
    receipt_directory = _plain_path(Path(receipt_directory))
    report = json.loads((receipt_directory/'receipt.json').read_text('utf8'))
    if (report.get('format') != 'runtime-install-receipt' or report.get('version') != 1
            or report.get('state') != 'installed'
            or not re.fullmatch(r'[A-Z]{4}-[0-9]{5}_[0-9A-F]{8}',report['stem'])):
        raise ValueError('Invalid runtime rollback receipt')
    _, folders = profile_folders(report['profile'])
    if {k:str(v) for k,v in folders.items()} != report['folders']:
        raise ValueError('Runtime profile folders changed since installation')
    plan=[]; seen=set()
    for row in report['files']:
        kind=row['kind']
        if kind not in folders or kind in seen:raise ValueError('Invalid/duplicate runtime rollback target')
        seen.add(kind)
        expected=folders[kind]/(report['stem']+('.ini' if kind=='gamesettings' else '.pnach'))
        target=_plain_path(Path(row['target']))
        if target!=expected or _state(target) is None or _sha(target.read_bytes())!=row['after_sha256']:
            raise ValueError('Runtime rollback target changed')
        before=None
        if row['backup'] is not None:
            backup=_plain_path(receipt_directory/row['backup'])
            if not backup.is_relative_to(receipt_directory/'before'):
                raise ValueError('Runtime rollback backup escaped receipt')
            before=backup.read_bytes()
            if _sha(before)!=row['before_sha256']:raise ValueError('Runtime rollback backup changed')
        elif row['before_sha256'] is not None:raise ValueError('Runtime rollback backup missing')
        plan.append((target,before))
    for target,before in plan:
        if before is None:target.unlink()
        else:_atomic_write(target,before)
        if _state(target)!=before:raise ValueError('Runtime rollback readback mismatch')
    report['state']='rolled-back';_save_receipt(receipt_directory,report)
    return report
