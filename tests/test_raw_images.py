"""RGB24 pipeline uses synthetic pixels; no retail assets are required."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mysticnights.artwork import digest
from mysticnights.raw_images import make_raw_delta, apply_raw_delta, validate_raw_images, build_raw_images


class RawImageTests(unittest.TestCase):
    def setUp(self):
        self.before = bytes(range(72))
        after = bytearray(self.before); after[21:27] = b"\xff\0\xff\0\xff\0"
        self.after = bytes(after)
        self.rects = [[1, 1, 2, 1]]
        self.patch = make_raw_delta(self.before, self.after, [6, 4, 3], self.rects, {"label": "Title"})

    def fixture(self):
        recipe = {"format": "raw-image-slots", "version": 1, "images": [{"resource": "BG.RGB",
                  "sha256": digest(self.before), "profile": [6,4,3], "slots": [{"id": "label", "rect": self.rects[0]}]}]}
        catalogue = {"format": "raw-image-translations", "version": 1,
                     "entries": [{"id":"label", "target":"Title", "status":"reviewed"}], "artwork_patches":[self.patch]}
        return recipe, catalogue

    def test_roundtrip_and_protected_pixels(self):
        self.assertEqual(apply_raw_delta(self.before, self.patch, targets={"label":"Title"}), self.after)
        self.assertEqual(apply_raw_delta(self.after, self.patch, reverse=True), self.before)
        self.assertEqual(self.before[:21], self.after[:21]); self.assertEqual(self.before[27:], self.after[27:])

    def test_bad_identity_profile_version_size_and_targets(self):
        for k,v in [("format","bad"),("version",2),("size",71),("profile",[6,4,4]),
                    ("profile",[True,4,3]),("profile",[6,0,3]),("source_sha256","0"*64),("modified_sha256","0"*64)]:
            with self.subTest(k=k,v=v):
                patch=deepcopy(self.patch);patch[k]=v
                with self.assertRaises(ValueError): apply_raw_delta(self.before,patch)
        with self.assertRaises(ValueError): apply_raw_delta(self.after,self.patch)
        with self.assertRaises(ValueError): apply_raw_delta(self.before,self.patch,targets={"label":"Changed"})

    def test_invalid_ranges_expected_bytes_and_rectangle(self):
        mutations=[lambda p:p["ranges"].append(p["ranges"][0]),lambda p:p.update(ranges=[]),
                   lambda p:p["ranges"][0].update(byte_offset=True),lambda p:p["ranges"][0].update(byte_offset=-1),
                   lambda p:p["ranges"][0].update(byte_offset=72),lambda p:p["ranges"][0].update(before=[256]),
                   lambda p:p["ranges"][0].update(after=[True]),lambda p:p["ranges"][0].update(before=[0]),
                   lambda p:p.update(allowed_rectangles=[[0,0,1,1]])]
        for mutate in mutations:
            patch=deepcopy(self.patch);mutate(patch)
            with self.assertRaises(ValueError): apply_raw_delta(self.before,patch)

    def test_compiler_rejects_outside_empty_and_size(self):
        for after in [self.before, self.after[:-1], bytes([99])+self.after[1:]]:
            with self.assertRaises(ValueError): make_raw_delta(self.before,after,[6,4,3],self.rects,{"label":"Title"})
        with self.assertRaises(ValueError): make_raw_delta(self.before,self.after,[6,4,3],[[-1,1,2,1]],{})

    def test_build_and_conflict(self):
        recipe,catalogue=self.fixture()
        image=type("Fixture",(),{"read":lambda _,path:self.before})()
        result,report=build_raw_images(image,recipe,catalogue,{"other":b"keep"})
        self.assertEqual(result,{"other":b"keep","BG.RGB":self.after})
        self.assertEqual(report,{"installed_slots":["label"],"changed_resources":["BG.RGB"]})
        with self.assertRaises(ValueError): build_raw_images(image,recipe,catalogue,{"BG.RGB":self.after})

    def test_coverage_and_binding_rejects_drift(self):
        recipe,catalogue=self.fixture()
        for mutate in [lambda r,c:r.update(format="bad"),lambda r,c:c.update(version=9),
                       lambda r,c:r["images"].append(r["images"][0]),
                       lambda r,c:c["entries"].append(c["entries"][0]),lambda r,c:c["entries"][0].update(status="todo"),
                       lambda r,c:c["entries"][0].update(target=""),lambda r,c:c["entries"][0].update(target="Changed"),
                       lambda r,c:c.update(artwork_patches=[]),lambda r,c:c["artwork_patches"].append(c["artwork_patches"][0]),
                       lambda r,c:r["images"][0].update(profile=[4,6,3]),
                       lambda r,c:r["images"][0]["slots"][0].update(rect=[2,1,2,1])]:
            r,c=deepcopy(recipe),deepcopy(catalogue);mutate(r,c)
            with self.assertRaises(ValueError):validate_raw_images(r,c)


if __name__ == "__main__": unittest.main()
