from copy import deepcopy
import unittest
from PIL import Image,ImageDraw
from mysticnights.artwork_checks import check_size_groups

class SizeGroupTests(unittest.TestCase):
    def fixture(self):
        im=Image.new('RGBA',(100,50));d=ImageDraw.Draw(im)
        d.rectangle((5,3,40,15),fill=(240,140,40,255));d.rectangle((5,27,55,39),fill=(240,140,40,255))
        members=[{'rect':[0,y,80,22],'rgba_min':[180,70,0,100],'rgba_max':[255,255,255,255]}for y in [0,25]]
        check={'id':'peers','members':members,'min_row_pixels':5,'min_column_pixels':2,'max_height_difference':0,'expected_height':13}
        return im,check
    def test_equal_glyph_height_different_label_lengths(self):
        im,c=self.fixture();self.assertEqual(check_size_groups(im,[c])[0]['heights'],[13,13])
    def test_shrunken_row_missing_ink_and_expected_height(self):
        im,c=self.fixture();ImageDraw.Draw(im).rectangle((5,27,55,28),fill=(0,0,0,0))
        with self.assertRaisesRegex(ValueError,'peer heights'):check_size_groups(im,[c])
        c.pop('expected_height');c['max_height_difference']=2
        self.assertEqual(check_size_groups(im,[c])[0]['heights'],[13,11])
        c['expected_height']=13
        with self.assertRaisesRegex(ValueError,'expected'):check_size_groups(im,[c])
    def test_invalid_duplicate_and_too_few(self):
        im,c=self.fixture()
        for key,value in [('id',''),('members',[]),('max_height_difference',-1),('expected_height',True)]:
            bad=deepcopy(c);bad[key]=value
            with self.assertRaises(ValueError):check_size_groups(im,[bad])
        with self.assertRaises(ValueError):check_size_groups(im,[c,c])
    def test_original_material_highlight_exclusion_and_validation(self):
        im,c=self.fixture();im.putpixel((79,0),(240,140,40,255))
        c['min_row_pixels']=1;c['min_column_pixels']=1
        with self.assertRaises(ValueError):check_size_groups(im,[c])
        c['members'][0]['exclude_points']=[[79,0]]
        self.assertEqual(check_size_groups(im,[c])[0]['heights'],[13,13])
        for points in ([[79,0],[79,0]], [[80,0]], [[1]], [['x',1]]):
            bad=deepcopy(c);bad['members'][0]['exclude_points']=points
            with self.assertRaises(ValueError):check_size_groups(im,[bad])
