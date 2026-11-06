"""Check shipped HD authoring data without requiring proprietary game inputs."""
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf8"))


class HdArtworkCatalogueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.slots = read(ROOT / "assets/graphics-text-slots.json")["textures"]
        cls.recipe = read(ROOT / "locales/zh-CN/hd-artwork.json")

    def test_references_include_exact_source_member_location(self):
        for row in self.recipe["textures"]:
            ref = row["reference"]
            with self.subTest(reference=ref):
                self.assertTrue({"resource", "member", "offset", "size"} <= ref.keys())
                matches = [s for s in self.slots if any(
                    all(r.get(k) == ref[k] for k in ("resource", "member", "offset", "size"))
                    for r in s["references"])]
                self.assertEqual(len(matches), 1)

    def test_native_hash_is_bound_to_current_localized_delta(self):
        for row in self.recipe["textures"]:
            ref = row["reference"]
            matches = [s for s in self.slots if any(
                r["resource"] == ref["resource"] and r["member"] == ref["member"]
                for r in s["references"])]
            self.assertEqual(len(matches), 1)
            delta = read(ROOT / "locales/zh-CN/artwork" / (matches[0]["sha256"][:12] + ".json"))
            self.assertEqual(row["source_sha256"], delta["modified_sha256"])
            self.assertEqual(row["base_delta"]["source_sha256"], row["source_sha256"])

    def test_layers_are_covered_by_declared_regions(self):
        for row in self.recipe["textures"]:
            for layer in row["layers"]:
                x, y, w, h = layer["rect"]
                self.assertTrue(any(ax <= x and ay <= y and x + w <= ax + aw and y + h <= ay + ah
                                    for ax, ay, aw, ah in row["allowed_hd_rectangles"]))
                self.assertEqual(sum(run[0] for run in layer["pixels_rle"]), w * h)

    def test_layer_ids_and_rectangles_are_disjoint(self):
        for row in self.recipe["textures"]:
            ids = [layer["id"] for layer in row["layers"]]
            self.assertEqual(len(ids), len(set(ids)))
            rects = [layer["rect"] for layer in row["layers"]]
            for i, (x, y, w, h) in enumerate(rects):
                for ax, ay, aw, ah in rects[i + 1:]:
                    self.assertFalse(max(x, ax) < min(x + w, ax + aw) and
                                     max(y, ay) < min(y + h, ay + ah))


if __name__ == "__main__":
    unittest.main()
