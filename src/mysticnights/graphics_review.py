"""Closed source inventory for an explicit human artwork review.

Hash and reference closure are machine-verified. The disposition text records
human review, not automatic OCR or a claim of in-game visual acceptance.
"""
from collections import Counter
import hashlib
from pathlib import PurePosixPath
from .graphics import decode_tim2
from .resources import parse_res


DISPOSITIONS = {'localized-readable-text', 'runtime-font-atlas',
                'retain-unreadable-or-identifier', 'no-readable-localizable-prose',
                'retain-original-user-request'}


def validate_review(review, graphics, image=None):
    if review.get('format') != 'graphics-source-review' or review.get('version') != 1:
        raise ValueError('Unsupported graphics source review')
    records = {r['sha256']: r for r in review['textures']}
    if len(records) != len(review['textures']):
        raise ValueError('Duplicate graphics review texture')
    localized = {t['sha256'] for t in graphics['textures']}
    reviewed = {k for k, r in records.items() if r['disposition'] == 'localized-readable-text'}
    if reviewed != localized:
        raise ValueError('Graphics source review/localized texture coverage mismatch')
    # Some meshes embed the same sign under STxxxx_xxx instead of the Gxxx
    # atlas name. Filename suffix closure alone cannot express that relation.
    # Families are source-bound human/pixel-reviewed declarations, not OCR or
    # an automatic claim that all similar-looking surfaces are equivalent.
    families=review.get('visual_families',[])
    if not isinstance(families,list):
        raise ValueError('Graphics visual family declarations require a list')
    family_ids=set()
    for family in families:
        if not isinstance(family,dict):
            raise ValueError('Invalid graphics visual family')
        ident=family.get('id');members=family.get('members');evidence=family.get('evidence')
        if (not isinstance(ident,str) or not ident.strip() or ident in family_ids
                or not isinstance(evidence,str) or not evidence.strip()
                or not isinstance(members,list) or len(members)<2
                or any(not isinstance(k,str) or k not in records for k in members)
                or len(members)!=len(set(members))):
            raise ValueError('Invalid graphics visual family identity/members/evidence')
        family_ids.add(ident)
        if any(k not in localized for k in members):
            raise ValueError('Unlocalized graphics visual family member requires explicit review')
    physical = set()
    for row in records.values():
        if row['disposition'] not in DISPOSITIONS or not row.get('review_note', '').strip() or not row['references']:
            raise ValueError('Missing graphics review disposition/evidence')
        for ref in row['references']:
            key = ref['resource'], ref['member']
            if key in physical:
                raise ValueError('Duplicate graphics review physical member')
            physical.add(key)
    summary = {'unique_textures': len(records), 'physical_members': len(physical),
               'dispositions': dict(sorted(Counter(r['disposition'] for r in records.values()).items()))}
    if summary != review['summary'] or review['source_iso_sha256'] != graphics['source_iso_sha256']:
        raise ValueError('Graphics source review summary/identity mismatch')
    suffixes = review.get('filename_variant_suffixes', ['_C'])
    def family(name):
        p = PurePosixPath(name)
        stem = p.stem
        for suffix in suffixes:
            if stem.endswith(suffix):
                stem = stem[:-len(suffix)]
                break
        return str(p.with_name(stem + p.suffix))
    localized_families = {family(r['member']) for k in localized for r in records[k]['references']}
    for key, row in records.items():
        if key not in localized and any(family(r['member']) in localized_families for r in row['references']):
            raise ValueError('Unlocalized member-name/colored texture variant requires explicit review')
    if image is not None:
        actual = {}
        for resource in sorted(image.files):
            if not resource.endswith('.RES'):
                continue
            payload = image.read(resource)
            archive = parse_res(payload)
            resource_sha = hashlib.sha256(payload).hexdigest()
            for member in archive.entries:
                if not member.name.endswith('.TM2'):
                    continue
                data = archive.read(member)
                key = hashlib.sha256(data).hexdigest()
                if key not in actual:
                    _, info = decode_tim2(data)
                    actual[key] = {'profile': [info[k] for k in ('width', 'height', 'image_type', 'clut_type')], 'references': []}
                actual[key]['references'].append({'resource': resource, 'member': member.name,
                    'resource_sha256': resource_sha, 'offset': member.offset, 'size': member.size})
        if set(actual) != set(records):
            raise ValueError('Source TIM2 inventory is incomplete or contains unknown textures')
        for key, row in actual.items():
            if (row['profile'] != records[key]['profile']
                    or sorted(row['references'], key=lambda r: (r['resource'], r['member']))
                    != sorted(records[key]['references'], key=lambda r: (r['resource'], r['member']))):
                raise ValueError('Source TIM2 profile/reference mismatch')
    return summary
