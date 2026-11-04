"""Artist importer preserves and enforces optional state checks before writing."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from test_graphics import tim2_fixture,digest
from mysticnights.graphics import decode_tim2
from mysticnights.artwork import apply_artwork

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
import import_artwork


class ImportArtworkTests(unittest.TestCase):
    def run_import(self, invalid=False):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=tim2_fixture();(root/"source.tm2").write_bytes(source)
            im,_=decode_tim2(source)
            for x in range(10,13):im.putpixel((x,10),(255,255,255,255))
            im.save(root/"artist.png")
            selector={"rect":[10,10,3,1],"rgba_min":[200,200,200,200],"rgba_max":[255,255,255,255]}
            selected={**selector,"rect":[0,0,3,1]} if invalid else selector
            checks=[{"id":"pair","normal":selector,"selected":selected,
                     "min_row_pixels":1,"min_column_pixels":1,
                     "max_width_difference":0,"max_height_difference":0}]
            recipe={"allowed_rectangles":[[10,10,3,1]],"targets":{"a":"A"},"state_checks":checks}
            (root/"recipe.json").write_text(json.dumps(recipe),"utf8")
            output=root/"delta.json"
            argv=["import_artwork.py","--source",str(root/"source.tm2"),"--source-sha256",digest(source),
                  "--png",str(root/"artist.png"),"--recipe",str(root/"recipe.json"),"--output",str(output)]
            with patch.object(sys,"argv",argv),contextlib.redirect_stdout(io.StringIO()):
                if invalid:
                    with self.assertRaisesRegex(ValueError,"no measurable ink"):import_artwork.main()
                    self.assertFalse(output.exists())
                else:
                    import_artwork.main();data=json.loads(output.read_text("utf8"))
                    self.assertEqual(data["state_checks"],checks)
                    modified=apply_artwork(source,data)
                    self.assertEqual(apply_artwork(modified,data,reverse=True),source)

    def test_checks_retained_and_round_trip(self):self.run_import()
    def test_failed_check_does_not_publish(self):self.run_import(invalid=True)


if __name__=="__main__":unittest.main()
