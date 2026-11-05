"""Filesystem-only installation/rollback; no emulator executable or game input."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from mysticnights.runtime_install import install_package, rollback_install, profile_folders


class RuntimeInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.profile=self.root/'profile';self.package=self.root/'package'
        (self.profile/'inis').mkdir(parents=True)
        self.ini=self.profile/'inis/PCSX2.ini'
        self.ini.write_text('[Folders]\nPatches = custom-patches\nCheats = user\\custom-cheats\n\n[EmuCore]\nEnableCheats = false\n','utf8')
        self.stem='TEST-12345_1234ABCD';files=[]
        for kind,body in [('patches','[Wide]\npatch=1,EE,00100000,word,00000000\n'),
                          ('cheats','[HP]\npatch=1,EE,00100004,word,00000000\n')]:
            name=f'localized/{kind}/{self.stem}.pnach';p=self.package/name;p.parent.mkdir(parents=True)
            data=body.encode('utf8');p.write_bytes(data)
            files.append({'path':name,'size':len(data),'sha256':hashlib.sha256(data).hexdigest()})
        meta={'format':'runtime-patch-package','version':1,'recipe':{'serial':'TEST-12345'},
              'identities':[{'role':'localized','crc':'1234ABCD'}],'files':files}
        (self.package/'manifest.json').write_text(json.dumps(meta),'utf8')
        self.receipt=self.root/'receipt'

    def snapshot(self):
        return {p.relative_to(self.profile).as_posix():p.read_bytes() for p in self.profile.rglob('*') if p.is_file()}

    def install(self,**kwargs):
        return install_package(self.package,self.profile,self.receipt,**kwargs)

    def test_custom_folders_game_only_settings_and_byte_identical_rollback(self):
        before=self.snapshot()
        report=self.install(enabled_patches=['Wide'],allow_cheats=True)
        self.assertEqual(len(report['files']),3)
        self.assertEqual(report['enabled_cheat_groups'],[])
        self.assertEqual((self.profile/'custom-patches'/f'{self.stem}.pnach').read_bytes(),
                         (self.package/'localized/patches'/f'{self.stem}.pnach').read_bytes())
        self.assertTrue((self.profile/'user/custom-cheats'/f'{self.stem}.pnach').is_file())
        self.assertEqual(self.ini.read_bytes(),before['inis/PCSX2.ini'])
        game=(self.profile/'gamesettings'/f'{self.stem}.ini').read_text('utf8')
        self.assertIn('EnableCheats = true',game);self.assertIn('Enable = Wide',game)
        self.assertNotIn('[Cheats]',game)
        self.assertEqual(rollback_install(self.receipt)['state'],'rolled-back')
        self.assertEqual(self.snapshot(),before)

    def test_existing_pnach_is_backed_up_and_restored(self):
        p=self.profile/'custom-patches'/f'{self.stem}.pnach';p.parent.mkdir();p.write_bytes(b'old user patches\r\n')
        before=self.snapshot();report=self.install()
        self.assertEqual(len(report['files']),2)
        self.assertEqual((self.receipt/report['files'][0]['backup']).read_bytes(),b'old user patches\r\n')
        rollback_install(self.receipt);self.assertEqual(self.snapshot(),before)

    def test_corrupt_package_fails_before_writing_any_profile_file(self):
        (self.package/'localized/cheats'/f'{self.stem}.pnach').write_bytes(b'wrong')
        before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'integrity'):self.install()
        self.assertEqual(self.snapshot(),before);self.assertFalse(self.receipt.exists())

    def test_existing_game_preferences_are_not_overwritten(self):
        p=self.profile/'gamesettings'/f'{self.stem}.ini';p.parent.mkdir();p.write_bytes(b'[EmuCore]\nUserSetting=true\n')
        before=self.snapshot()
        with self.assertRaisesRegex(FileExistsError,'per-game'):self.install(enabled_patches=['Wide'])
        self.assertEqual(self.snapshot(),before);self.assertFalse(self.receipt.exists())

    def test_unknown_group_role_and_duplicate_folder_fail_closed(self):
        for options in ({'enabled_patches':['Missing']},{'enabled_patches':['Wide','Wide']},{'role':'other'}):
            with self.assertRaises(ValueError):self.install(**options)
        self.ini.write_text('[Folders]\nPatches=one\nPatches=two\n','utf8')
        with self.assertRaisesRegex(ValueError,'duplicate'):profile_folders(self.profile)
        self.assertFalse(self.receipt.exists())

    def test_rollback_rejects_modified_target_before_any_restore(self):
        report=self.install();p=Path(report['files'][1]['target']);p.write_bytes(b'user edited after install')
        before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'target changed'):rollback_install(self.receipt)
        self.assertEqual(self.snapshot(),before)

    def test_rollback_rejects_backup_and_destination_tampering(self):
        p=self.profile/'custom-patches'/f'{self.stem}.pnach';p.parent.mkdir();p.write_bytes(b'previous')
        report=self.install();before=self.snapshot()
        backup=self.receipt/report['files'][0]['backup'];backup.write_bytes(b'wrong backup')
        with self.assertRaisesRegex(ValueError,'backup changed'):rollback_install(self.receipt)
        self.assertEqual(self.snapshot(),before)
        backup.write_bytes(b'previous');report['files'][0]['target']=str(self.root/'unrelated.pnach')
        (self.receipt/'receipt.json').write_text(json.dumps(report),'utf8')
        with self.assertRaisesRegex(ValueError,'target changed'):rollback_install(self.receipt)
        self.assertEqual(self.snapshot(),before)

    def test_mid_install_error_restores_preexisting_state(self):
        import mysticnights.runtime_install as module
        before=self.snapshot();actual=module._atomic_write;writes=0
        def failing(path,data):
            nonlocal writes
            if path.suffix=='.pnach':
                writes+=1
                if writes==2:raise OSError('injected write failure')
            return actual(path,data)
        with patch.object(module,'_atomic_write',side_effect=failing):
            with self.assertRaisesRegex(OSError,'injected'):self.install()
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(json.loads((self.receipt/'receipt.json').read_text('utf8'))['state'],'aborted-restored')

    def test_links_missing_profile_and_used_receipt_rejected(self):
        with self.assertRaises(ValueError):profile_folders(self.root/'missing')
        self.install()
        with self.assertRaises(FileExistsError):self.install()
        link=self.root/'linked-profile'
        try:link.symlink_to(self.profile,target_is_directory=True)
        except OSError:return
        with self.assertRaisesRegex(ValueError,'link/junction'):profile_folders(link)


if __name__=='__main__':unittest.main()
