"""Scene-embedded names must not bypass explicitly reviewed visual families."""
from copy import deepcopy
from collections import Counter
import unittest
from mysticnights.graphics_review import validate_review


def fixture():
    a,b='a'*64,'b'*64
    records=[{'sha256':a,'disposition':'localized-readable-text','review_note':'readable sign',
              'references':[{'resource':'RES/A.RES','member':'G269.TM2'}]},
             {'sha256':b,'disposition':'no-readable-localizable-prose','review_note':'old mistaken classification',
              'references':[{'resource':'RES/B.RES','member':'ST0101_042.TM2'}]}]
    review={'format':'graphics-source-review','version':1,'source_iso_sha256':'c'*64,
            'summary':{'unique_textures':2,'physical_members':2,
                       'dispositions':dict(sorted(Counter(r['disposition']for r in records).items()))},
            'textures':records,'visual_families':[{'id':'caution-door','members':[a,b],
                       'evidence':'same source sign; separately named embedded atlas'}]}
    graphics={'source_iso_sha256':'c'*64,'textures':[{'sha256':a}]}
    return review,graphics


class VisualFamilyTests(unittest.TestCase):
    def test_scene_member_renaming_cannot_hide_a_readable_sibling(self):
        review,graphics=fixture()
        with self.assertRaisesRegex(ValueError,'visual family'):
            validate_review(review,graphics)
        review['textures'][1]['disposition']='localized-readable-text'
        review['summary']['dispositions']={'localized-readable-text':2}
        graphics['textures'].append({'sha256':'b'*64})
        self.assertEqual(validate_review(review,graphics)['unique_textures'],2)

    def test_visual_family_identity_members_and_evidence_are_guarded(self):
        review,graphics=fixture()
        # Keep the family complete before exercising malformed declarations.
        review['textures'][1]['disposition']='localized-readable-text'
        review['summary']['dispositions']={'localized-readable-text':2}
        graphics['textures'].append({'sha256':'b'*64})
        for mutation in (
            lambda r:r.update(visual_families=None),
            lambda r:r['visual_families'][0].update(id=''),
            lambda r:r['visual_families'][0].update(members=['a'*64,'a'*64]),
            lambda r:r['visual_families'][0].update(members=['a'*64,'d'*64]),
            lambda r:r['visual_families'][0].update(evidence=''),
            lambda r:r['visual_families'].append(deepcopy(r['visual_families'][0])),
        ):
            bad=deepcopy(review);mutation(bad)
            with self.assertRaises(ValueError):validate_review(bad,graphics)


if __name__=='__main__':unittest.main()
