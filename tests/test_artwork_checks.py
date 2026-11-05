"""Synthetic paired-label checks do not require the retail disc."""
from copy import deepcopy
import unittest
from PIL import Image, ImageDraw
from mysticnights.artwork_checks import check_state_pairs, check_clear_regions


class StateCheckTests(unittest.TestCase):
    def setUp(self):
        self.image = Image.new("RGBA", (80,32), (0,0,0,0))
        draw=ImageDraw.Draw(self.image)
        draw.rectangle((10,5,25,18),fill=(220,100,30,255))
        draw.rectangle((50,5,65,18),fill=(220,220,180,255))
        def select(rect,low,high):
            return {"rect":rect,"rgba_min":low,"rgba_max":high}
        self.check={"id":"pair", "min_row_pixels":8, "min_column_pixels":2,
                    "normal":select([0,0,40,20],[160,55,0,128],[255,255,109,255]),
                    "selected":select([40,0,40,20],[160,135,100,128],[255,255,255,255]),
                    "max_width_difference":2,"max_height_difference":1,
                    "horizontal_runs":[{**select([40,20,40,4],[160,135,100,128],[255,255,255,255]),"maximum":12}]}

    def test_equal_states_and_isolated_glint(self):
        self.image.putpixel((42,6),(255,255,255,255))
        row=check_state_pairs(self.image,[self.check])[0]
        self.assertEqual(row["normal"]["width"],16)
        self.assertEqual(row["selected"]["width"],16)
        self.assertEqual(row["horizontal_runs"],[0])

    def test_shrunken_glyph_and_frame_contamination(self):
        draw=ImageDraw.Draw(self.image)
        draw.rectangle((40,0,79,19),fill=(0,0,0,0))
        draw.rectangle((52,7,63,16),fill=(220,220,180,255))
        draw.line((44,22,74,22),fill=(220,220,180,255))
        with self.assertRaisesRegex(ValueError,"width.*height.*horizontal run"):
            check_state_pairs(self.image,[self.check])

    def test_added_underline_alone(self):
        ImageDraw.Draw(self.image).line((44,22,74,22),fill=(220,220,180,255))
        with self.assertRaisesRegex(ValueError,"horizontal run 31"):
            check_state_pairs(self.image,[self.check])

    def test_oversized_and_missing_ink_rejected(self):
        for box in ((40,0,79,19),None):
            im=self.image.copy();d=ImageDraw.Draw(im);d.rectangle((40,0,79,19),fill=(0,0,0,0))
            if box:d.rectangle(box,fill=(220,220,180,255))
            with self.assertRaises(ValueError):check_state_pairs(im,[self.check])

    def test_invalid_recipe_and_duplicate_id(self):
        for field,value in (("rect",[-1,0,40,20]),("rect",[40,0,41,20]),
                            ("rgba_min",[256,0,0,0]),("rgba_max",[20,20,20,20])):
            c=deepcopy(self.check);c["selected"][field]=value
            with self.assertRaises(ValueError):check_state_pairs(self.image,[c])
        for key,value in (("max_width_difference",-1),("min_row_pixels",True),("id","")):
            c=deepcopy(self.check);c[key]=value
            with self.assertRaises(ValueError):check_state_pairs(self.image,[c])
        with self.assertRaises(ValueError):check_state_pairs(self.image,[self.check,self.check])

    def test_transparent_gutters_reject_even_a_dim_old_halo(self):
        check={"id":"gutter","rect":[0,24,80,8],"max_alpha":0}
        self.assertEqual(check_clear_regions(self.image,[check])[0]["nontransparent_pixels"],0)
        self.image.putpixel((3,25),(60,2,8,1))
        with self.assertRaisesRegex(ValueError,"gutter: nontransparent pixels=1"):
            check_clear_regions(self.image,[check])

    def test_clear_region_validation(self):
        check={"id":"edge","rect":[0,24,80,8],"max_alpha":0}
        self.image.putpixel((3,25),(200,40,20,4))
        with self.assertRaises(ValueError):check_clear_regions(self.image,[check])
        check["max_alpha"]=4
        self.assertEqual(len(check_clear_regions(self.image,[check])),1)
        for key,value in (("max_alpha",255),("max_alpha",True),("id",""),("rect",[0,31,80,2])):
            bad=deepcopy(check);bad[key]=value
            with self.assertRaises(ValueError):check_clear_regions(self.image,[bad])
        with self.assertRaises(ValueError):check_clear_regions(self.image,[check,check])


if __name__=="__main__":unittest.main()
