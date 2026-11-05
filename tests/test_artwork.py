"""Authored-art patches are tested without retail assets or network access."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from test_graphics import tim2_fixture, res_fixture, font_fixture, digest
from mysticnights.artwork import make_artwork_delta, apply_artwork, load_graphics_catalogue, import_indexed_pixels
from mysticnights.graphics import build_graphics, decode_tim2
from mysticnights.resources import parse_res


class ArtworkTests(unittest.TestCase):
    def setUp(self):
        self.source = tim2_fixture()
        output = bytearray(self.source)
        output[64 + 10 * 32 + 10:64 + 10 * 32 + 13] = b"\x01\x01\x01"
        self.output = bytes(output)
        self.patch = make_artwork_delta(self.source, self.output, [[8, 8, 10, 8]], {"label": "A"})

    def test_forward_reverse_and_no_change_outside_pixels(self):
        self.assertEqual(apply_artwork(self.source, self.patch, targets={"label": "A"}), self.output)
        self.assertEqual(apply_artwork(self.output, self.patch, reverse=True), self.source)
        self.assertEqual(self.source[:64], self.output[:64])
        self.assertEqual(self.source[64+32*24:], self.output[64+32*24:])

    def test_forward_enforces_optional_state_checks_but_reverse_restores_source(self):
        selector={"rect":[10,10,3,1],"rgba_min":[200,200,200,200],"rgba_max":[255,255,255,255]}
        self.patch["state_checks"]=[{"id":"pair","normal":selector,"selected":deepcopy(selector),
                                      "min_row_pixels":1,"min_column_pixels":1,
                                      "max_width_difference":0,"max_height_difference":0}]
        self.assertEqual(apply_artwork(self.source,self.patch),self.output)
        self.assertEqual(apply_artwork(self.output,self.patch,reverse=True),self.source)
        self.patch["clear_regions"]=[{"id":"outer","rect":[10,10,3,1],"max_alpha":0}]
        with self.assertRaisesRegex(ValueError,"clear-region.*nontransparent pixels=3"):
            apply_artwork(self.source,self.patch)
        self.assertEqual(apply_artwork(self.output,self.patch,reverse=True),self.source)
        self.patch.pop("clear_regions")
        self.patch["state_checks"][0]["selected"]["rect"]=[0,0,3,1]
        with self.assertRaisesRegex(ValueError,"no measurable ink"):
            apply_artwork(self.source,self.patch)

    def test_import_identity_keeps_duplicate_palette_indices(self):
        source=bytearray(self.source);source[64]=7
        source=bytes(source);image,_=decode_tim2(source)
        self.assertEqual(import_indexed_pixels(source,image,[],source_sha256=digest(source)),source)

    def test_import_exact_color_and_round_trip(self):
        image,_=decode_tim2(self.source)
        image.putpixel((10,10),(255,255,255,255))
        result=import_indexed_pixels(self.source,image,[[10,10,1,1]],source_sha256=digest(self.source))
        self.assertEqual(result[64+10*32+10],1)
        patch=make_artwork_delta(self.source,result,[[10,10,1,1]],{"a":"A"})
        self.assertEqual(apply_artwork(result,patch,reverse=True),self.source)

    def test_import_rejects_source_and_dimensions(self):
        image,_=decode_tim2(self.source)
        with self.assertRaisesRegex(ValueError,"source identity"):
            import_indexed_pixels(self.source,image,[],source_sha256="0"*64)
        for bad in (image.convert("RGB"),image.resize((31,24))):
            with self.assertRaisesRegex(ValueError,"dimensions"):
                import_indexed_pixels(self.source,bad,[],source_sha256=digest(self.source))

    def test_import_rejects_protected_and_bad_rectangle(self):
        image,_=decode_tim2(self.source);image.putpixel((0,0),(255,255,255,255))
        for rect in ([],[[1,1,1,1]],[[-1,0,2,2]],[[0,0,33,24]]):
            with self.assertRaises(ValueError):
                import_indexed_pixels(self.source,image,rect,source_sha256=digest(self.source))

    def test_import_transparent_rgb_is_not_a_needless_delta(self):
        source=bytearray(self.source);source[64+768:64+768+4]=bytes([120,10,20,0])
        source=bytes(source);image,_=decode_tim2(source);image.putpixel((0,0),(0,0,0,0))
        self.assertEqual(import_indexed_pixels(source,image,[[0,0,1,1]],source_sha256=digest(source)),source)

    def test_import_premultiplied_alpha_does_not_pick_opaque_fringe(self):
        source=bytearray(self.source)
        # index2 is transparent cyan; index3 is opaque dark blue. Straight-RGB
        # comparison incorrectly selects index3 for low-opacity blue edges.
        start=64+768
        source[start+8:start+12]=bytes([0,100,255,4])
        source[start+12:start+16]=bytes([0,5,15,128])
        source=bytes(source);image,_=decode_tim2(source)
        image.putpixel((0,0),(0,5,15,8))
        result=import_indexed_pixels(source,image,[[0,0,1,1]],source_sha256=digest(source))
        self.assertEqual(result[64],2)

    def test_wrong_source_output_and_text_rejected(self):
        with self.assertRaises(ValueError): apply_artwork(self.output, self.patch)
        with self.assertRaises(ValueError): apply_artwork(self.source, self.patch, targets={"label": "B"})
        for key,value in [("format", "bad"), ("version", 2), ("modified_sha256", "0"*64), ("profile", [1,1,5,3]), ("size", 1)]:
            p=deepcopy(self.patch);p[key]=value
            with self.assertRaises(ValueError): apply_artwork(self.source,p)

    def test_bad_ranges_and_palette_writes_rejected(self):
        for change in [lambda p:p["ranges"].append(p["ranges"][0]),
                       lambda p:p["ranges"][0].update(pixel_offset=32*24),
                       lambda p:p["ranges"][0].update(pixel_offset=True),
                       lambda p:p["ranges"][0].update(before=[256]),
                       lambda p:p["ranges"][0].update(after=[True]),
                       lambda p:p["ranges"][0].update(before=[1,1,1]),
                       lambda p:p.update(ranges=[]),
                       lambda p:p.update(allowed_rectangles=[[0,0,2,2]])]:
            p=deepcopy(self.patch);change(p)
            with self.assertRaises(ValueError): apply_artwork(self.source,p)

    def test_compiler_rejects_structure_and_unapproved_pixel(self):
        for position in [1, 64, len(self.source)-1]:
            changed=bytearray(self.source);changed[position]^=1
            with self.assertRaises(ValueError): make_artwork_delta(self.source,bytes(changed),[[8,8,10,8]],{"label":"A"})

    def test_catalogue_file_paths_and_embedded_patch_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/"artwork").mkdir()
            (root/"artwork/test.json").write_text(json.dumps(self.patch),encoding="utf8")
            path=root/"graphics.json"
            path.write_text(json.dumps({"artwork_files":["artwork/test.json"]}),encoding="utf8")
            self.assertEqual(load_graphics_catalogue(path)["artwork_patches"],[self.patch])
            for bad in ["../other.json", "C:/outside.json", "artwork/a/b.json", "artwork\\test.json", 123]:
                path.write_text(json.dumps({"artwork_files":[bad]}),encoding="utf8")
                with self.assertRaises(ValueError): load_graphics_catalogue(path)

    def fixture(self):
        source=res_fixture(self.source);member=parse_res(source).get("A.TM2")
        texture={"sha256":digest(self.source),"profile":[32,24,5,3],"rendering":"authored-delta",
                 "artwork_rectangles":self.patch["allowed_rectangles"],"slots":[{"id":"label","install":True}],
                 "references":[{"resource":"A.RES","resource_sha256":digest(source),"member":"A.TM2","offset":member.offset,"size":member.size}]}
        manifest={"format":"graphics-text-slots","version":1,"art_direction":"source-style-only","textures":[texture]}
        font=font_fixture()
        locale={"format":"graphics-translations","version":1,"locale":"xx","font_sha256":digest(font),
                "entries":[{"id":"label","status":"draft","target":"A"}],"artwork_patches":[self.patch]}
        image=type("Fixture",(),{"read":lambda _,path:source})()
        return image,manifest,locale,font

    def run_build(self, image, manifest, locale, font):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"font.ttf";path.write_bytes(font)
            return build_graphics(image,manifest,locale,path)

    def test_authored_integration_and_duplicate_physical_member(self):
        image,manifest,locale,font=self.fixture()
        output,report=self.run_build(image,manifest,locale,font)
        self.assertEqual(parse_res(output["A.RES"]).read("A.TM2"),self.output)
        self.assertEqual(report["installed_slots"],["label"])
        self.patch["clear_regions"]=[{"id":"dirty","rect":[10,10,3,1],"max_alpha":0}]
        with self.assertRaisesRegex(ValueError,"clear-region"):
            self.run_build(image,manifest,locale,font)
        self.patch.pop("clear_regions")
        duplicate=deepcopy(manifest["textures"][0]);duplicate["slots"]=[{"id":"second","install":True}]
        manifest["textures"].append(duplicate)
        locale["entries"].append({"id":"second","status":"draft","target":"B"})
        with self.assertRaisesRegex(ValueError,"duplicate physical"):
            self.run_build(image,manifest,locale,font)

    def test_missing_unused_and_changed_authored_art_rejected(self):
        for change in [lambda m,l:l.update(artwork_patches=[]),
                       lambda m,l:l["entries"][0].update(target="B"),
                       lambda m,l:m["textures"][0].update(artwork_rectangles=[[1,1,2,2]]),
                       lambda m,l:m["textures"][0].pop("rendering")]:
            image,manifest,locale,font=self.fixture();change(manifest,locale)
            with self.assertRaises(ValueError): self.run_build(image,manifest,locale,font)


if __name__=="__main__":unittest.main()
