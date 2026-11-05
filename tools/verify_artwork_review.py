"""Verify closed artwork inspection ledger and known old-pattern regressions."""
import argparse,json,hashlib
from pathlib import Path
from _bootstrap import ROOT
from mysticnights.iso9660 import IsoImage
from mysticnights.resources import parse_res
from mysticnights.graphics import decode_tim2
from mysticnights.versions import load_version,verify_original


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--original',type=Path,required=True);p.add_argument('--iso',type=Path,required=True);p.add_argument('--review',type=Path,default=ROOT/'assets/artwork-quality-review.json');p.add_argument('--material-only',action='store_true');a=p.parse_args()
 quality=json.loads(a.review.read_text('utf8'));slots=json.loads((ROOT/'assets/graphics-text-slots.json').read_text('utf8'));source=verify_original(a.original,load_version(ROOT/'assets/game-version.json'));actual=IsoImage(a.iso)
 specs={t['sha256']:t for t in slots['textures']};rows={t['source_sha256']:t for t in quality['textures']};checks=quality['material_regressions']
 if quality.get('format')!='artwork-quality-review'or quality.get('version')!=1 or quality['source_iso_sha256']!=slots['source_iso_sha256']:raise ValueError('Unsupported inspection source/format')
 if len(rows)!=len(quality['textures'])or set(rows)!=set(specs):raise ValueError('Inspection ledger is not closed')
 if not checks or len({(c['source_sha256'],c['id'])for c in checks})!=len(checks)or any(c['source_sha256']not in specs for c in checks):raise ValueError('Empty/duplicate/unknown material regression samples')
 cache={};members=0;retained=[];samplecount=0
 def read(iso,ref):
  key=(str(iso.path),ref['resource'])
  if key not in cache:cache[key]=parse_res(iso.read(ref['resource']))
  return cache[key].read(ref['member'])
 for key,t in specs.items():
  for ref in t['references']:
   src=read(source,ref);dst=read(actual,ref);assert hashlib.sha256(src).hexdigest()==key
   if not a.material_only and hashlib.sha256(dst).hexdigest()!=rows[key]['localized_sha256']:raise ValueError('Inspection is stale: '+ref['member'])
   members+=1
  relevant=[c for c in checks if c['source_sha256']==key]
  if not relevant:continue
  src=read(source,t['references'][0]);dst=read(actual,t['references'][0]);im,info=decode_tim2(src)
  for c in relevant:
   x,y,w,h=c['rect'];offset=info['pixel_offset'];stride=info['width']
   if not(0<=x<x+w<=im.width and 0<=y<y+h<=im.height):raise ValueError('Invalid regression rectangle')
   def block(b):return b''.join(b[offset+yy*stride+x:offset+yy*stride+x+w]for yy in range(y,y+h))
   blocksrc=block(src)
   if hashlib.sha256(blocksrc).hexdigest()!=c['source_sample_sha256']:raise ValueError('Regression source fingerprint changed')
   if blocksrc==block(dst):retained.append(key[:12]+'/'+c['id'])
   samplecount+=1
 print(f'ARTWORK MATERIAL {"FAIL"if retained else"PASS"} retained_source_patterns={len(retained)}/{samplecount}')
 if retained:raise ValueError('Retained known old patterns: '+','.join(retained))
 print(f'ARTWORK REVIEW PASS unique={len(rows)} physical={members} ledger=closed provenance=offline-not-game-approval')


if __name__=='__main__':main()
