"""Explicit, guarded, reversible PCSX2 texture-pack file installation.

Only a manifest's SERIAL/replacements/*.png files are managed. The explicit
profile's Folders/Textures may resolve outside that profile. Global INI bytes,
unrelated textures, BIOS, saves and emulator processes are never written/run.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile


class TextureInstallError(ValueError):
    """The pack/profile/receipt fails an identity or path invariant."""


_PACK_MANIFESTS={'hd-font-manifest.json':'pcsx2-hd-main-font-pack',
                 'hd-artwork-manifest.json':'pcsx2-hd-artwork-pack'}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _plain_path(value) -> Path:
    """Check lexical ancestors before resolving '..'; reject all reparse points."""
    path=Path(value)
    if not path.is_absolute():
        path=Path.cwd()/path
    current=Path(path.anchor)
    parts=path.parts[1:]
    for index,part in enumerate(parts):
        if part=='..':
            current=current.parent
            continue
        current=current/part
        try:
            info=current.lstat()
        except FileNotFoundError:
            continue
        if (stat.S_ISLNK(info.st_mode)
                or getattr(info,'st_file_attributes',0) & getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0x400)
                or getattr(current,'is_junction',lambda:False)()):
            raise TextureInstallError('Texture install path contains a link/reparse point')
        if index<len(parts)-1 and not stat.S_ISDIR(info.st_mode):
            raise TextureInstallError('Texture install ancestor is not a directory')
    return path.resolve()


def _state(path: Path) -> bytes | None:
    path=_plain_path(path)
    if not path.exists():
        return None
    if not path.is_file():
        raise TextureInstallError('Texture target is not a regular file')
    return path.read_bytes()


def _json(data: bytes) -> dict:
    def pairs(rows):
        result={}
        for key,value in rows:
            if key in result:
                raise TextureInstallError('Duplicate JSON object field')
            result[key]=value
        return result
    try:
        result=json.loads(data.decode('utf-8-sig'),object_pairs_hook=pairs)
    except (UnicodeError,json.JSONDecodeError) as exc:
        raise TextureInstallError('Invalid texture JSON metadata') from exc
    if not isinstance(result,dict):
        raise TextureInstallError('Texture metadata must be an object')
    return result


def profile_textures(directory) -> tuple[Path,Path]:
    root=_plain_path(directory)
    ini=_plain_path(root/'inis/PCSX2.ini')
    if not root.is_dir() or not ini.is_file():
        raise TextureInstallError('Expected existing PCSX2 profile with inis/PCSX2.ini')
    section=''; value=None
    for line in ini.read_text(encoding='utf-8-sig').splitlines():
        line=line.strip()
        if line.startswith('[') and line.endswith(']'):
            section=line[1:-1].casefold()
        elif section=='folders' and '=' in line and not line.startswith((';','#')):
            key,text=(part.strip() for part in line.split('=',1))
            if key.casefold()!='textures':
                continue
            if value is not None or not text or any(c in text for c in '\x00\r\n'):
                raise TextureInstallError('Invalid/duplicate PCSX2 texture folder')
            value=text
    path=Path((value or 'textures').replace('\\',os.sep))
    if os.name=='nt' and bool(path.drive)!=bool(path.root):
        raise TextureInstallError('Ambiguous drive-relative PCSX2 texture folder')
    folder=_plain_path(path if path.is_absolute() else root/path)
    if folder.exists() and not folder.is_dir():
        raise TextureInstallError('Texture folder is not a directory')
    return root,folder


def _manifest_rows(metadata: dict) -> tuple[str,list[dict]]:
    if (metadata.get('format') not in _PACK_MANIFESTS.values()
            or type(metadata.get('version')) is not int or metadata['version']!=1):
        raise TextureInstallError('Unknown texture pack manifest format')
    serial=metadata.get('serial')
    if not isinstance(serial,str) or not re.fullmatch(r'[A-Z]{4}-[0-9]{5}',serial):
        raise TextureInstallError('Invalid texture pack serial')
    rows=metadata.get('textures'); scale=metadata.get('scale')
    if (not isinstance(rows,list) or not rows or type(scale) is not int or not 1<=scale<=16):
        raise TextureInstallError('Invalid texture pack file list or scale')
    seen=set()
    for row in rows:
        if not isinstance(row,dict):
            raise TextureInstallError('Invalid texture pack entry')
        name=row.get('filename'); relative=row.get('path'); png=row.get('png')
        if not isinstance(name,str) or not re.fullmatch(r'[0-9a-f]{1,16}-[0-9a-f]{1,16}-[0-9a-f]{8}\.png',name):
            raise TextureInstallError('Invalid exact-key texture filename')
        expected=f'{serial}/replacements/{name}'
        if relative!=expected or str(PurePosixPath(relative))!=relative:
            raise TextureInstallError('Texture path does not match serial/replacements/filename')
        if relative.casefold() in seen:
            raise TextureInstallError('Duplicate texture package path')
        seen.add(relative.casefold())
        if not isinstance(png,dict) or not re.fullmatch(r'[0-9a-f]{64}',str(png.get('sha256',''))):
            raise TextureInstallError('Invalid texture PNG SHA-256')
        if any(type(png.get(key)) is not int or png[key]<=0 for key in ('size','width','height')):
            raise TextureInstallError('Invalid texture PNG size/dimensions')
        for key in ('width','height'):
            if type(row.get(key)) is not int or row[key]<16 or row[key]*scale!=png[key] or png[key]>16384:
                raise TextureInstallError('Texture scale/dimensions disagree')
        try:
            key=f"{int(row['texture_hash'],16):x}-{int(row['palette_hash'],16):x}-{int(row['bits'],16):08x}.png"
        except (KeyError,TypeError,ValueError) as exc:
            raise TextureInstallError('Invalid texture key fields') from exc
        if key!=name:
            raise TextureInstallError('Texture key fields disagree with filename')
    return serial,rows


def _check_png(data: bytes, row: dict) -> None:
    if len(data)!=row['png']['size'] or _sha(data)!=row['png']['sha256']:
        raise TextureInstallError('Texture source PNG integrity mismatch')
    from PIL import Image,UnidentifiedImageError
    try:
        with Image.open(io.BytesIO(data)) as image:
            if (image.format!='PNG' or image.mode!='RGBA'
                    or image.size!=(row['png']['width'],row['png']['height'])):
                raise TextureInstallError('Texture source PNG profile mismatch')
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.load()
    except (UnidentifiedImageError,OSError,SyntaxError) as exc:
        raise TextureInstallError('Invalid source PNG data') from exc


def _atomic_write(path: Path, data: bytes) -> None:
    _plain_path(path.parent); _plain_path(path)
    fd,temporary=tempfile.mkstemp(prefix='.texture-install-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _save(directory: Path, report: dict) -> None:
    data=(json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode('utf8')
    _atomic_write(directory/'receipt.json',data)
    if _state(directory/'receipt.json')!=data:
        raise TextureInstallError('Texture receipt readback mismatch')


def _overlap(a: Path,b: Path) -> bool:
    return a.is_relative_to(b) or b.is_relative_to(a)


def _mkdir_chain(path: Path) -> list[Path]:
    missing=[]; cursor=_plain_path(path)
    while not cursor.exists():
        missing.append(cursor); cursor=cursor.parent
    if not cursor.is_dir():
        raise TextureInstallError('Texture output ancestor is not a directory')
    created=[]
    for directory in reversed(missing):
        _plain_path(directory)
        try:
            directory.mkdir(); created.append(directory)
        except FileExistsError:
            if not directory.is_dir():
                raise
    return created


def _prune_created(directories: list[Path]) -> None:
    for directory in reversed(directories):
        _plain_path(directory)
        try:
            directory.rmdir()
        except (FileNotFoundError,OSError):
            # Unrelated files/directories added since install are never deleted.
            continue


def _recover(attempted: list, *, desired_before: bool) -> None:
    # Preflight recovery too: never overwrite a third, concurrently edited state.
    for target,before,after in attempted:
        if _state(target) not in (before,after):
            raise TextureInstallError('Texture transaction recovery target changed')
    for target,before,after in reversed(attempted):
        wanted=before if desired_before else after
        if _state(target)==wanted:
            continue
        if wanted is None:
            target.unlink()
        else:
            _atomic_write(target,wanted)
        if _state(target)!=wanted:
            raise TextureInstallError('Texture transaction recovery readback mismatch')


def install_package(package, data_directory, receipt_directory) -> dict:
    package=_plain_path(package); receipt=_plain_path(receipt_directory)
    root,folder=profile_textures(data_directory)
    if receipt.exists():
        raise FileExistsError('Texture receipt directory already exists')
    if _overlap(receipt,package) or _overlap(receipt,folder):
        raise TextureInstallError('Texture receipt overlaps package/destination')
    candidates=[(name,_state(package/name)) for name in _PACK_MANIFESTS]
    candidates=[(name,data) for name,data in candidates if data is not None]
    if len(candidates)!=1:
        raise TextureInstallError('Texture package requires exactly one recognized manifest; missing/ambiguous')
    manifest_name,metadata_bytes=candidates[0]
    metadata=_json(metadata_bytes)
    if metadata.get('format')!=_PACK_MANIFESTS[manifest_name]:
        raise TextureInstallError('Texture manifest filename/format disagree')
    serial,rows=_manifest_rows(metadata)
    owned_directory=folder/serial/'replacements'
    if _overlap(package,folder/serial):
        raise TextureInstallError('Texture package overlaps installed serial directory')
    ini=root/'inis/PCSX2.ini'; ini_before=_state(ini)
    plan=[]
    for row in rows:
        source=_plain_path(package/PurePosixPath(row['path']))
        if not source.is_relative_to(package):
            raise TextureInstallError('Texture package source escaped root')
        data=_state(source)
        if data is None:
            raise TextureInstallError('Texture source PNG missing')
        _check_png(data,row)
        target=_plain_path(folder/PurePosixPath(row['path']))
        if target.parent!=owned_directory:
            raise TextureInstallError('Texture target escaped owned replacements directory')
        plan.append((target,_state(target),data))
    # All source files and every existing destination are validated before a
    # receipt or target directory is created.
    receipt.mkdir(parents=True)
    (receipt/'before').mkdir()
    _atomic_write(receipt/'package-manifest.json',metadata_bytes)
    if _state(receipt/'package-manifest.json')!=metadata_bytes:
        raise TextureInstallError('Texture manifest snapshot readback mismatch')
    records=[]
    for index,((target,before,data),source_row) in enumerate(zip(plan,rows)):
        backup=None
        if before is not None:
            backup=f'before/{index}.png'
            _atomic_write(receipt/backup,before)
            if _state(receipt/backup)!=before:
                raise TextureInstallError('Texture backup readback mismatch')
        records.append({'path':source_row['path'],'target':str(target),'after_sha256':_sha(data),'after_size':len(data),
                        'before_sha256':None if before is None else _sha(before),
                        'before_size':None if before is None else len(before),'backup':backup})
    report={'format':'texture-pack-install-receipt','version':1,'state':'prepared',
            'profile':str(root),'textures_directory':str(folder),'serial':serial,
            'package_manifest_filename':manifest_name,
            'package_manifest_sha256':_sha(metadata_bytes),'files':records,'created_directories':[],
            'global_ini_sha256':_sha(ini_before)}
    _save(receipt,report)
    attempted=[]; created=[]
    try:
        if _state(ini)!=ini_before or profile_textures(root)[1]!=folder:
            raise TextureInstallError('Global INI changed during texture installation')
        for target,before,data in plan:
            if _state(target)!=before:
                raise TextureInstallError('Texture target changed during installation')
        created=_mkdir_chain(owned_directory)
        report['created_directories']=[str(path) for path in created]
        _save(receipt,report)
        for target,before,data in plan:
            if _state(target)!=before:
                raise TextureInstallError('Texture target changed during installation')
            attempted.append((target,before,data))
            _atomic_write(target,data)
            if _state(target)!=data:
                raise TextureInstallError('Installed texture PNG readback mismatch')
        if _state(ini)!=ini_before:
            raise TextureInstallError('Global INI changed during texture installation')
        report['state']='installed'; _save(receipt,report)
    except BaseException:
        try:
            _recover(attempted,desired_before=True)
            _prune_created(created)
            report['state']='aborted-restored'; _save(receipt,report)
        except BaseException:
            report['state']='recovery-blocked'; _save(receipt,report)
            raise
        raise
    return report


def rollback_install(receipt_directory) -> dict:
    receipt=_plain_path(receipt_directory)
    report=_json(_state(receipt/'receipt.json') or b'{}')
    if (report.get('format')!='texture-pack-install-receipt'
            or type(report.get('version')) is not int or report['version']!=1
            or report.get('state')!='installed'):
        raise TextureInstallError('Invalid texture rollback receipt state/format')
    metadata_bytes=_state(receipt/'package-manifest.json')
    if metadata_bytes is None or _sha(metadata_bytes)!=report.get('package_manifest_sha256'):
        raise TextureInstallError('Texture rollback manifest snapshot changed')
    metadata=_json(metadata_bytes); serial,source_rows=_manifest_rows(metadata)
    manifest_name=report.get('package_manifest_filename','hd-font-manifest.json')
    if _PACK_MANIFESTS.get(manifest_name)!=metadata.get('format'):
        raise TextureInstallError('Texture rollback manifest filename/format disagree')
    root,folder=profile_textures(report.get('profile',''))
    if str(folder)!=report.get('textures_directory') or serial!=report.get('serial'):
        raise TextureInstallError('Texture folder changed since installation')
    rows=report.get('files')
    if not isinstance(rows,list) or len(rows)!=len(source_rows):
        raise TextureInstallError('Texture rollback must include complete manifest-owned file list')
    plan=[]; seen=set()
    for index,(row,source) in enumerate(zip(rows,source_rows)):
        if not isinstance(row,dict) or row.get('path')!=source['path'] or row.get('path') in seen:
            raise TextureInstallError('Invalid/duplicate texture rollback target')
        seen.add(row['path'])
        expected=_plain_path(folder/PurePosixPath(source['path']))
        target=_plain_path(row.get('target',''))
        if target!=expected:
            raise TextureInstallError('Texture rollback target path changed')
        after=_state(target)
        if (after is None or row.get('after_sha256')!=source['png']['sha256']
                or row.get('after_size')!=source['png']['size']
                or len(after)!=row['after_size'] or _sha(after)!=row['after_sha256']):
            raise TextureInstallError('Texture rollback target changed')
        before=None
        if row.get('backup') is not None:
            if row['backup']!=f'before/{index}.png':
                raise TextureInstallError('Invalid texture rollback backup path')
            backup=_plain_path(receipt/row['backup'])
            before=_state(backup)
            if before is None or len(before)!=row.get('before_size') or _sha(before)!=row.get('before_sha256'):
                raise TextureInstallError('Texture rollback backup changed')
        elif row.get('before_size') is not None or row.get('before_sha256') is not None:
            raise TextureInstallError('Texture rollback backup missing')
        plan.append((target,before,after))
    created=[]; allowed={folder,folder/serial,folder/serial/'replacements',*folder.parents}
    for value in report.get('created_directories',[]):
        path=_plain_path(value)
        if path not in allowed or path in created:
            raise TextureInstallError('Invalid texture rollback directory record')
        created.append(path)
    # Every after-file, path and backup is checked above before the first write.
    attempted=[]
    try:
        for target,before,after in plan:
            if _state(target)!=after:
                raise TextureInstallError('Texture rollback target changed after preflight')
            attempted.append((target,before,after))
            if before is None:
                target.unlink()
            else:
                _atomic_write(target,before)
            if _state(target)!=before:
                raise TextureInstallError('Texture rollback readback mismatch')
        report['state']='rolled-back'; _save(receipt,report)
    except BaseException:
        try:
            _recover(attempted,desired_before=False)
            report['state']='installed'; _save(receipt,report)
        except BaseException:
            report['state']='recovery-blocked'; _save(receipt,report)
            raise
        raise
    _prune_created(created)
    return report
