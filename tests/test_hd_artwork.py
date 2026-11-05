"""Fresh authored HD pixel layers tested with synthetic indexed TIM2/RES."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools')]
from mysticnights.artwork import make_artwork_delta
from mysticnights.hd_artwork import build_texture,bind_sources
from mysticnights.hd_font import raw_atlas
from mysticnights.resources import parse_res
from test_font import tim2_fixture
from test_resources import fixture as res_fixture


def sha(data):return hashlib.sha256(data).hexdigest()


def art_fixture():
    data=bytearray(tim2_fixture())
    struct.pack_into('<Q',data,40,(19<<20)|(8<<26)|(8<<30))
    data[64:65600]=bytes([255])*65536
    source=bytes(data); clean=bytearray(source); clean[64+1+256]=0
    delta=make_artwork_delta(source,bytes(clean),[[1,1,1,1]],{'material':'glyph-free'})
    row={'source_sha256':sha(source),'base_delta':delta,'allowed_hd_rectangles':[[4,4,12,8]],
         'layers':[{'id':'fresh','rect':[4,4,4,4],'mode':'replace-region','pixels_rle':[[16,[240,80,20,64]]]},
                   {'id':'mask','rect':[8,4,4,4],'mode':'rgb-mask-keep-alpha','pixels_rle':[[16,[255,0,0,128]]]}]}
    return source,bytes(clean),row


class HdArtworkTests(unittest.TestCase):
    def test_fresh_replace_and_mask_blend_keep_raw_alpha_and_protected_material(self):
        source,clean,row=art_fixture(); image,report=build_texture(source,row,scale=4)
        self.assertEqual(image.size,(1024,1024))
        self.assertEqual(image.getpixel((4,4)),(240,80,20,64))
        old=raw_atlas(clean).getpixel((2,1))
        expected=tuple((c*128+old[k]*127+127)//255 for k,c in enumerate((255,0,0)))+(old[3],)
        self.assertEqual(image.getpixel((8,4)),expected)
        self.assertEqual(image.getpixel((8,4))[3],128)
        self.assertEqual(image.getpixel((0,0)),raw_atlas(source).getpixel((0,0)))
        self.assertEqual(report['base_roundtrip'],'byte-identical')
        self.assertEqual(report['outside_allowed'],'raw RGBA byte-identical to final-native nearest')
        self.assertEqual(report['outside_layers'],'raw RGBA byte-identical to glyph-free-base nearest')
        # Coverage is authored at HD pixels, not constrained to native 4x blocks.
        alternate=deepcopy(row); alternate['layers'][0]['pixels_rle']=[[1,[240,80,20,64]],[15,[0,0,0,0]]]
        other,_=build_texture(source,alternate,scale=4)
        self.assertNotEqual(other.getpixel((4,4)),other.getpixel((5,4)))

    def test_source_base_delta_and_scale_are_guarded(self):
        source,clean,row=art_fixture()
        for change in (lambda p:p.update(source_sha256='0'*64),
                       lambda p:p['base_delta'].update(modified_sha256='0'*64)):
            bad=deepcopy(row); change(bad)
            with self.assertRaises(ValueError): build_texture(source,bad,scale=4)
        with self.assertRaises(ValueError):build_texture(source,row,scale=3)
        self.assertEqual(sha(source),row['source_sha256'])

    def test_rgba_mask_blends_raw_peak_alpha_not_coverage_times_ps2_alpha(self):
        source,clean,row=art_fixture()
        layer=row['layers'][1];layer.update(mode='rgba-mask',alpha_peak=105)
        layer['pixels_rle']=[[1,[255,0,0,255]],[15,[255,0,0,128]]]
        image,proof=build_texture(source,row,scale=4)
        self.assertEqual(image.getpixel((8,4)),(255,0,0,105))
        expected=(105*128+128*127+127)//255
        self.assertEqual(image.getpixel((9,4))[3],expected)
        self.assertEqual(proof['layers'][1]['alpha_peak'],105)
        for value in (None,-1,256,True):
            bad=deepcopy(row);bad['layers'][1]['alpha_peak']=value
            with self.assertRaisesRegex(ValueError,'alpha_peak'):build_texture(source,bad,scale=4)

    def test_layer_bounds_coverage_overlap_and_duplicate_ids_fail(self):
        source,clean,row=art_fixture()
        for change in (lambda p:p['layers'][0].update(rect=[-1,4,4,4]),
                       lambda p:p['layers'][0].update(rect=[4,4,1024,4]),
                       lambda p:p['layers'][0].update(rect=[0,0,4,4]),
                       lambda p:p['layers'][1].update(rect=[5,4,4,4]),
                       lambda p:p['layers'][1].update(id='fresh'),
                       lambda p:p['layers'][0].update(mode='source-over')):
            bad=deepcopy(row); change(bad)
            with self.assertRaises(ValueError): build_texture(source,bad,scale=4)

    def test_rle_requires_exact_positive_runs_and_raw_byte_channels(self):
        source,clean,row=art_fixture()
        for rle in ([],[[0,[1,2,3,4]]],[[True,[1,2,3,4]]],[[15,[1,2,3,4]]],
                    [[17,[1,2,3,4]]],[[16,[1,2,3]]],[[16,[1,2,3,256]]],[[16,[1,2,3,True]]]):
            bad=deepcopy(row); bad['layers'][0]['pixels_rle']=rle
            with self.assertRaises(ValueError):build_texture(source,bad,scale=4)

    def test_base_material_change_outside_allowed_hd_regions_is_rejected(self):
        source,clean,row=art_fixture(); row['allowed_hd_rectangles']=[[5,4,11,8]]
        row['layers'][0].update(rect=[5,4,3,4],pixels_rle=[[12,[240,80,20,64]]])
        with self.assertRaisesRegex(ValueError,'outside allowed'):build_texture(source,row,scale=4)

    def test_binding_checks_iso_manifest_resource_and_exact_member_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            image,manifest,recipe,version=self.binding_fixture(Path(directory))
            bound=bind_sources(image,manifest,recipe,version)
            self.assertEqual(len(bound),1); self.assertEqual(bound[0][1],art_fixture()[0])
            bad=deepcopy(recipe); bad['textures'][0]['reference']['offset']+=1
            with self.assertRaisesRegex(ValueError,'reference'):bind_sources(image,manifest,bad,version)
            bad=deepcopy(manifest);bad['modified']['sha256']='0'*64
            with self.assertRaisesRegex(ValueError,'ISO'):bind_sources(image,bad,recipe,version)
            bad=deepcopy(manifest);bad['changed_files'][0]['sha256']='0'*64
            with self.assertRaisesRegex(ValueError,'resource'):bind_sources(image,bad,recipe,version)

    def test_duplicate_overlapping_and_alias_reference_paths_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            image,manifest,recipe,version=self.binding_fixture(Path(directory))
            recipe['textures'].append(deepcopy(recipe['textures'][0]))
            with self.assertRaisesRegex(ValueError,'overlap|duplicate'):bind_sources(image,manifest,recipe,version)
            recipe['textures'].pop();recipe['textures'][0]['reference']['resource']='RES/../RES/SYSTEM.RES'
            with self.assertRaisesRegex(ValueError,'path'):bind_sources(image,manifest,recipe,version)

    def test_pack_fresh_output_exact_png_readback_and_installer_compatibility(self):
        import build_hd_artwork
        from mysticnights.texture_install import install_package,rollback_install
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); image,manifest,recipe,version=self.binding_fixture(root)
            (root/'assets').mkdir();(root/'assets/game-version.json').write_text(json.dumps(version),encoding='utf8')
            m=root/'build.json';m.write_text(json.dumps(manifest),encoding='utf8')
            r=root/'recipe.json';r.write_text(json.dumps(recipe),encoding='utf8')
            output=root/'pack'
            with patch.object(build_hd_artwork,'ROOT',root),patch.object(build_hd_artwork,'IsoImage',return_value=image):
                report=build_hd_artwork.build_pack(image.path,m,r,output,hash_function=lambda data:len(data))
                with self.assertRaises(FileExistsError):build_hd_artwork.build_pack(image.path,m,r,output)
            self.assertEqual(report['format'],'pcsx2-hd-artwork-pack')
            self.assertEqual(len(report['textures']),1)
            self.assertEqual(build_hd_artwork.verify_pack(output),report)
            profile=root/'profile';(profile/'inis').mkdir(parents=True)
            (profile/'inis/PCSX2.ini').write_bytes(b'[Folders]\nTextures=textures\n')
            receipt=root/'receipt';self.assertEqual(install_package(output,profile,receipt)['state'],'installed')
            self.assertEqual(rollback_install(receipt)['state'],'rolled-back')

    def binding_fixture(self,root):
        source,clean,row=art_fixture(); resource=res_fixture({0:[('A.TM2',source)]})
        archive=parse_res(resource); entry=archive.get('A.TM2')
        row['reference']={'resource':'RES/SYSTEM.RES','member':'A.TM2','offset':entry.offset,'size':entry.size}
        iso=root/'source.iso';iso.write_bytes(b'fixture image identity')
        cnf=b'fixture serial'; files={'RES/SYSTEM.RES':resource,'SYSTEM.CNF':cnf}
        image=SimpleNamespace(path=iso,size=iso.stat().st_size,read=lambda name:files[name],
                              get=lambda name:SimpleNamespace(offset=4096,size=len(files[name])))
        original={'size':image.size,'sha256':'f'*64}
        manifest={'original':dict(original),'modified':{'size':image.size,'sha256':sha(iso.read_bytes())},
                  'locale':'test','changed_files':[{'path':'RES/SYSTEM.RES','offset':4096,'size':len(resource),'sha256':sha(resource)}]}
        recipe={'format':'hd-artwork-recipe','version':1,'scale':4,'serial':'TEST-12345','textures':[row]}
        version={'serial':'TEST-12345','iso':original,'files':{'SYSTEM.CNF':{'size':len(cnf),'sha256':sha(cnf)}}}
        return image,manifest,recipe,version


if __name__=='__main__':unittest.main()
