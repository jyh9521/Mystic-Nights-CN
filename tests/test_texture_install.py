"""Guarded filesystem-only texture installation; no game or real profile input."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from mysticnights.texture_install import install_package, rollback_install, profile_textures


class TextureInstallTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.profile=self.root/"profile"; (self.profile/"inis").mkdir(parents=True)
        self.ini=self.profile/"inis/PCSX2.ini"
        self.ini.write_bytes(b"[Folders]\r\nTextures = ../shared/textures\r\n\r\n[GS]\r\nLoadTextureReplacements = true\r\n")
        self.textures=self.root/"shared/textures"
        self.package=self.root/"package"; self.package.mkdir()
        self.receipt=self.root/"receipt"
        self.serial="TEST-12345"; rows=[]
        for i in range(8):
            filename=f"{i+1:x}-abcdef-00001113.png"
            relative=f"{self.serial}/replacements/{filename}"
            path=self.package/relative; path.parent.mkdir(parents=True,exist_ok=True)
            Image.new("RGBA",(64,64),(i*20,80,100,100)).save(path)
            data=path.read_bytes()
            rows.append({"filename":filename,"texture_hash":f"{i+1:016x}","palette_hash":"0000000000abcdef",
                         "bits":"00001113","path":relative,"width":16,"height":16,
                         "png":{"size":len(data),"sha256":hashlib.sha256(data).hexdigest(),"width":64,"height":64}})
        self.meta={"format":"pcsx2-hd-main-font-pack","version":1,"serial":self.serial,"scale":4,"textures":rows}
        self.save_manifest()

    def save_manifest(self):
        (self.package/"hd-font-manifest.json").write_text(json.dumps(self.meta),encoding="utf8")

    def snapshot(self):
        return {p.relative_to(self.root).as_posix():p.read_bytes() for p in self.root.rglob('*')
                if p.is_file() and not p.is_relative_to(self.receipt)}

    def install(self):
        return install_package(self.package,self.profile,self.receipt)

    def test_external_relative_folder_eight_files_existing_new_and_rollback(self):
        path=self.textures/self.meta['textures'][0]['path']; path.parent.mkdir(parents=True)
        path.write_bytes(b'previous user PNG bytes\r\n')
        unrelated=self.textures/'OTHER-22222/replacements/unrelated.png'; unrelated.parent.mkdir(parents=True)
        unrelated.write_bytes(b'unrelated texture')
        before=self.snapshot(); report=self.install()
        self.assertEqual(report['state'],'installed'); self.assertEqual(len(report['files']),8)
        self.assertEqual(report['textures_directory'],str(self.textures.resolve()))
        self.assertEqual(self.ini.read_bytes(),before['profile/inis/PCSX2.ini'])
        for row in self.meta['textures']:
            self.assertEqual((self.textures/row['path']).read_bytes(),(self.package/row['path']).read_bytes())
        self.assertEqual((self.receipt/report['files'][0]['backup']).read_bytes(),b'previous user PNG bytes\r\n')
        self.assertEqual(rollback_install(self.receipt)['state'],'rolled-back')
        self.assertEqual(self.snapshot(),before)

    def test_default_texture_folder_is_profile_relative(self):
        self.ini.write_bytes(b'[Folders]\nCheats=cheats\n')
        root,folder=profile_textures(self.profile)
        self.assertEqual(folder,self.profile/'textures'); self.assertEqual(root,self.profile)

    def test_artwork_manifest_format_installs_and_rolls_back(self):
        old=self.package/'hd-font-manifest.json'; old.unlink()
        self.meta['format']='pcsx2-hd-artwork-pack'
        (self.package/'hd-artwork-manifest.json').write_text(json.dumps(self.meta),encoding='utf8')
        before=self.snapshot();report=self.install()
        self.assertEqual(report['package_manifest_filename'],'hd-artwork-manifest.json')
        self.assertEqual(rollback_install(self.receipt)['state'],'rolled-back')
        self.assertEqual(self.snapshot(),before)

    def test_ambiguous_manifests_or_wrong_filename_format_fail_closed(self):
        second=self.package/'hd-artwork-manifest.json';second.write_text(json.dumps(self.meta),encoding='utf8')
        with self.assertRaisesRegex(ValueError,'exactly one|ambiguous'):self.install()
        self.assertFalse(self.receipt.exists())
        (self.package/'hd-font-manifest.json').unlink()
        with self.assertRaisesRegex(ValueError,'filename/format'):self.install()
        self.assertFalse(self.receipt.exists());self.assertFalse(self.textures.exists())

    def test_corrupt_last_source_preflights_before_receipt_or_profile_changes(self):
        (self.package/self.meta['textures'][-1]['path']).write_bytes(b'corrupt')
        before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'integrity'): self.install()
        self.assertEqual(self.snapshot(),before); self.assertFalse(self.receipt.exists())

    def test_path_traversal_duplicate_and_filename_mismatch_rejected(self):
        original=json.loads(json.dumps(self.meta))
        edits=[lambda m:m['textures'][0].update(path='../escape.png'),
               lambda m:m['textures'].append(dict(m['textures'][0])),
               lambda m:m['textures'][0].update(filename='..\\escape.png'),
               lambda m:m['textures'][0].update(texture_hash='000000000000000f')]
        before=self.snapshot()
        for edit in edits:
            self.meta=json.loads(json.dumps(original)); edit(self.meta); self.save_manifest()
            with self.assertRaises(ValueError): self.install()
            self.assertFalse(self.receipt.exists()); self.assertFalse(self.textures.exists())
        self.meta=original; self.save_manifest(); self.assertEqual(self.snapshot(),before)

    def test_bad_png_profile_rejected_even_if_hashes_are_recomputed(self):
        row=self.meta['textures'][-1]; path=self.package/row['path']; path.write_bytes(b'not PNG')
        row['png']['sha256']=hashlib.sha256(path.read_bytes()).hexdigest(); row['png']['size']=path.stat().st_size
        self.save_manifest()
        with self.assertRaisesRegex(ValueError,'PNG'): self.install()
        self.assertFalse(self.receipt.exists()); self.assertFalse(self.textures.exists())

    def test_receipt_reuse_and_overlapping_receipt_are_rejected(self):
        self.install()
        with self.assertRaises(FileExistsError): self.install()
        with self.assertRaises(ValueError): install_package(self.package,self.profile,self.textures/'receipt')

    def test_last_target_tamper_blocks_all_restores(self):
        report=self.install(); Path(report['files'][-1]['target']).write_bytes(b'user changed target')
        before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'target changed'): rollback_install(self.receipt)
        self.assertEqual(self.snapshot(),before)

    def test_backup_tamper_blocks_all_restores(self):
        path=self.textures/self.meta['textures'][-1]['path']; path.parent.mkdir(parents=True)
        path.write_bytes(b'old last target'); report=self.install()
        (self.receipt/report['files'][-1]['backup']).write_bytes(b'corrupt backup')
        before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'backup changed'): rollback_install(self.receipt)
        self.assertEqual(self.snapshot(),before)

    def test_receipt_destination_and_missing_target_tampers_block_restore(self):
        report=self.install(); report['files'][-1]['target']=str(self.root/'unrelated.png')
        (self.receipt/'receipt.json').write_text(json.dumps(report),encoding='utf8')
        before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'target'): rollback_install(self.receipt)
        self.assertEqual(self.snapshot(),before)

    def test_owned_file_omission_and_manifest_snapshot_tampering_block_restore(self):
        report=self.install(); original=(self.receipt/'receipt.json').read_bytes()
        report['files'].pop(); (self.receipt/'receipt.json').write_text(json.dumps(report),encoding='utf8')
        before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'complete'): rollback_install(self.receipt)
        self.assertEqual(self.snapshot(),before)
        (self.receipt/'receipt.json').write_bytes(original)
        (self.receipt/'package-manifest.json').write_bytes(b'corrupt snapshot')
        with self.assertRaisesRegex(ValueError,'manifest'): rollback_install(self.receipt)
        self.assertEqual(self.snapshot(),before)

    def test_unrelated_global_ini_edit_preserved_but_changed_texture_folder_blocks(self):
        report=self.install(); original=self.ini.read_bytes()
        self.ini.write_bytes(original+b'UnrelatedSetting = new\r\n')
        latest=self.ini.read_bytes(); rollback_install(self.receipt)
        self.assertEqual(self.ini.read_bytes(),latest)
        new_receipt=self.root/'receipt2'
        install_package(self.package,self.profile,new_receipt)
        self.ini.write_bytes(b'[Folders]\nTextures = elsewhere\n')
        before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'folder changed'): rollback_install(new_receipt)
        self.assertEqual(self.snapshot(),before)

    def test_unrelated_added_file_in_owned_directory_is_retained(self):
        self.install(); added=self.textures/self.serial/'replacements/user-added.png'
        added.write_bytes(b'new unrelated file')
        rollback_install(self.receipt)
        self.assertEqual(added.read_bytes(),b'new unrelated file')

    def test_mid_install_failure_restores_existing_and_new_targets(self):
        import mysticnights.texture_install as module
        path=self.textures/self.meta['textures'][0]['path']; path.parent.mkdir(parents=True)
        path.write_bytes(b'old existing'); before=self.snapshot(); actual=module._atomic_write; count=0
        def fail(path,data):
            nonlocal count
            if path.parent==self.textures/self.serial/'replacements':
                count+=1
                if count==3: raise OSError('injected texture write failure')
            return actual(path,data)
        with patch.object(module,'_atomic_write',side_effect=fail):
            with self.assertRaisesRegex(OSError,'injected'): self.install()
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(json.loads((self.receipt/'receipt.json').read_text())['state'],'aborted-restored')

    def test_mid_rollback_failure_restores_installed_state_then_retry_succeeds(self):
        import mysticnights.texture_install as module
        path=self.textures/self.meta['textures'][-1]['path']; path.parent.mkdir(parents=True)
        path.write_bytes(b'previous'); self.install(); before=self.snapshot(); actual=module._atomic_write; count=0
        def fail(path,data):
            nonlocal count
            if path.parent==self.textures/self.serial/'replacements':
                count+=1
                if count==1: raise OSError('injected rollback failure')
            return actual(path,data)
        with patch.object(module,'_atomic_write',side_effect=fail):
            with self.assertRaisesRegex(OSError,'injected'): rollback_install(self.receipt)
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(json.loads((self.receipt/'receipt.json').read_text())['state'],'installed')
        self.assertEqual(rollback_install(self.receipt)['state'],'rolled-back')

    def test_nonregular_target_folder_and_duplicate_folder_fail_before_writes(self):
        path=self.textures/self.meta['textures'][-1]['path']; path.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError,'regular file'): self.install()
        self.assertFalse(self.receipt.exists())
        self.ini.write_bytes(b'[Folders]\nTextures=one\nTextures=two\n')
        with self.assertRaisesRegex(ValueError,'duplicate'): profile_textures(self.profile)

    def test_source_and_destination_links_are_rejected(self):
        link=self.root/'linked-package'
        try:
            link.symlink_to(self.package,target_is_directory=True)
        except OSError:
            # Windows normally requires Developer Mode for symbolic links.
            # Exercise S_IFLNK metadata deterministically; the next test creates
            # a real native NTFS junction to verify the host filesystem path.
            import stat
            actual=Path.lstat
            source=self.package/self.meta['textures'][-1]['path']
            def linked(path):
                return SimpleNamespace(st_mode=stat.S_IFLNK,st_file_attributes=0) if path==source else actual(path)
            with patch.object(Path,'lstat',linked):
                with self.assertRaisesRegex(ValueError,'link|reparse'): self.install()
            return
        with self.assertRaisesRegex(ValueError,'link|reparse'): install_package(link,self.profile,self.receipt)
        self.textures.parent.mkdir(parents=True)
        self.textures.symlink_to(self.root/'outside',target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'link|reparse'): self.install()

    @unittest.skipUnless(os.name=='nt','Windows junction profile guard')
    def test_native_windows_junction_is_rejected_without_touching_target(self):
        outside=self.root/'outside'; outside.mkdir(); (outside/'sentinel').write_bytes(b'unrelated')
        link=self.root/'linked-textures'
        quote=lambda p:"'"+str(p).replace("'","''")+"'"
        command=f"New-Item -ItemType Junction -Path {quote(link)} -Target {quote(outside)} | Out-Null"
        subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],check=True,capture_output=True)
        self.assertTrue(link.is_junction())
        self.ini.write_text('[Folders]\nTextures = '+str(link)+'\n',encoding='utf8')
        try:
            with self.assertRaisesRegex(ValueError,'link|reparse'): self.install()
            self.assertFalse(self.receipt.exists())
            self.assertEqual(list(outside.iterdir()),[outside/'sentinel'])
        finally:
            self.assertEqual(link.parent,self.root)
            link.rmdir()  # Remove only the verified fixture junction, not its target.


if __name__=='__main__': unittest.main()
