from PIL import Image
import unittest
from mysticnights.artwork_checks import check_shape_pairs


class ShapePairTests(unittest.TestCase):
    def fixture(self):
        im=Image.new('RGBA',(40,20));a=(250,150,10,209);b=(254,234,185,209)
        for x,y in [(0,0),(1,0),(0,1),(0,2),(1,2)]:
            im.putpixel((x+4,y+5),a);im.putpixel((x+24,y+5),b)
        spec={'id':'paired','normal':{'rect':[0,0,20,20],'rgba_min':list(a),'rgba_max':list(a),'center_twice':[10,13]},
              'selected':{'rect':[20,0,20,20],'rgba_min':list(b),'rgba_max':list(b),'center_twice':[50,13]},'max_center_error_twice':0}
        return im,spec

    def test_identical_color_variants_centered(self):
        im,spec=self.fixture();self.assertEqual(check_shape_pairs(im,[spec])[0]['silhouette'],'identical')

    def test_same_bounds_but_different_outline_rejected(self):
        im,spec=self.fixture();im.putpixel((25,6),(254,234,185,209))
        with self.assertRaisesRegex(ValueError,'silhouettes'):check_shape_pairs(im,[spec])

    def test_centered_shape_required_not_only_equal_dimensions(self):
        im,spec=self.fixture();spec['selected']['center_twice'][0]+=2
        with self.assertRaisesRegex(ValueError,'center error'):check_shape_pairs(im,[spec])

    def test_invalid_duplicate_shape_ids_and_empty_face(self):
        im,spec=self.fixture()
        with self.assertRaisesRegex(ValueError,'duplicate'):check_shape_pairs(im,[spec,spec])
        im.paste((0,0,0,0),(20,0,40,20))
        with self.assertRaisesRegex(ValueError,'no face'):check_shape_pairs(im,[spec])
