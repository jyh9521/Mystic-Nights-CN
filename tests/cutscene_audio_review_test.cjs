// Exercise the actual generated page script. This is logic replay, not a
// browser/game visual acceptance test and not actual human listening approval.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const htmlPath=process.argv[2];
if(!htmlPath)throw new Error('Pass a freshly generated listening review HTML');
const html=fs.readFileSync(htmlPath,'utf8');
const sourceText=html.match(/<script id="source" type="application\/json">([\s\S]*?)<\/script>/)[1];
const metaText=html.match(/<script id="audio-meta" type="application\/json">([\s\S]*?)<\/script>/)[1];
const source=JSON.parse(sourceText),meta=JSON.parse(metaText);
const scripts=[...html.matchAll(/<script(?:[^>]*)>([\s\S]*?)<\/script>/g)];
const script=scripts.at(-1)[1];
class Node{
 constructor(tag){this.tag=tag;this.children=[];this.handlers={};this.value='';this.checked=false;this.textContent='';}
 append(...nodes){this.children.push(...nodes)}
 addEventListener(type,fn){this.handlers[type]=fn}
 click(){this.handlers.click?.()}
}
const nodes=Object.fromEntries(['source','audio-meta','summary','export','saved','cards'].map(id=>['#'+id,new Node(id)]));
nodes['#source'].textContent=sourceText;nodes['#audio-meta'].textContent=metaText;
let blob=null,alerts=[];const storage={};
const allCues=source.resources.flatMap(r=>r.cues),firstSource=allCues[0];
storage['mystic-cutscene-audio-review-v2:'+meta.catalogue_sha256]=JSON.stringify({[firstSource.id]:{reviewed:true,text:firstSource.text,source_transcript:firstSource.source_transcript,end_frame_exclusive:980}});
const document={querySelector:selector=>nodes[selector],createElement:tag=>new Node(tag),createTextNode:t=>({textContent:t})};
vm.runInNewContext(script,{document,localStorage:{getItem:k=>storage[k],setItem:(k,v)=>storage[k]=v},
 URL:{createObjectURL:b=>(blob=b,'blob:unit'),revokeObjectURL:()=>{}},Blob,TextEncoder,
 setTimeout:fn=>fn(),alert:message=>alerts.push(message)});
const descendants=(n,tag)=>[...(n.tag===tag?[n]:[]),...(n.children||[]).flatMap(child=>descendants(child,tag))];
const cards=nodes['#cards'].children;
const number=card=>descendants(card,'input').find(n=>n.type==='number');
const checkbox=card=>descendants(card,'input').find(n=>n.type==='checkbox');
const textareas=card=>descendants(card,'textarea');
async function exported(){blob=null;nodes['#export'].click();assert.ok(blob,'Expected a downloadable JSON Blob');return JSON.parse(await blob.text())}
function identities(result){
 assert.equal(result.resources.length,47);
 const fields=['scene','resource','member','source_sha256','source_size','camera_resource','camera_member','camera_sha256','camera_frames'];
 for(let i=0;i<source.resources.length;i++){
  const a=source.resources[i],b=result.resources[i];
  for(const field of fields)assert.deepEqual(b[field],a[field]);
  if(!a.cues.length)assert.deepEqual(b,a,'Empty scenes must not become approved');
  for(let j=0;j<a.cues.length;j++){
   const x=a.cues[j],y=b.cues[j];
   for(const field of ['id','start_frame','source_audio_sha256','source_audio_id','asr','timing_samples','uncertain_audio_diagnostics'])assert.deepEqual(y[field],x[field]);
   assert.equal(Object.hasOwn(y.wav,'path'),Object.hasOwn(x.wav,'path'),'Local audio paths must not leak into exported catalogue');
  }
 }
 assert.equal(result.all_speech_transcribed,false);
 assert.equal(result.format,'cutscene-subtitle-catalogue');
}
(async()=>{
 assert.equal(cards.length,10);assert.equal(descendants(nodes['#cards'],'audio').length,10);
 assert.ok(cards.every(c=>checkbox(c).checked===false),'Old saved checked state must not be auto-restored');
 for(let i=0;i<cards.length;i++)assert.equal(descendants(cards[i],'audio')[0].src,meta.audio_map[allCues[i].source_audio_id].path);
 let result=await exported();identities(result);
 assert.equal(result.resources.flatMap(r=>r.cues).filter(c=>c.status==='reviewed').length,0);
 // Explicit checking with invalid timing must not make an importable cue.
 const first=cards[0],end=number(first),check=checkbox(first);
 end.value='';end.handlers.input();check.checked=true;check.handlers.change();blob=null;nodes['#export'].click();
 assert.equal(blob,null);assert.match(alerts.at(-1),/有效结束帧/);
 end.value=String(Number(end.max)+1);end.handlers.input();check.checked=true;check.handlers.change();blob=null;nodes['#export'].click();
 assert.equal(blob,null);assert.match(alerts.at(-1),/camera上界/);
 // Fill bounded test-only timing and missing lexical fields, without checking.
 for(let i=0;i<cards.length;i++){
  const card=cards[i],n=number(card);n.value=String(Math.min(allCues[i].start_frame+60,Number(n.max)));n.handlers.input();
  const areas=textareas(card);
  if(!areas[0].value.trim()){areas[0].value='test fixture vocalization';areas[0].handlers.input()}
  if(!areas[1].value.trim()){areas[1].value='测试字幕';areas[1].handlers.input()}
 }
 const draftFixture=await exported();identities(draftFixture);
 assert.ok(draftFixture.resources.flatMap(r=>r.cues).every(c=>c.status==='asr-draft'&&!c.human_listening_verified));
 // Each confirmation is a simulated click, solely for compiler compatibility.
 for(const card of cards){const c=checkbox(card);c.checked=true;c.handlers.change()}
 const reviewedFixture=await exported();identities(reviewedFixture);
 assert.equal(reviewedFixture.resources.flatMap(r=>r.cues).filter(c=>c.status==='reviewed'&&c.human_listening_verified).length,10);
 const text=textareas(first)[1];text.value='新意见';text.handlers.input();
 assert.equal(check.checked,false);result=await exported();identities(result);
 assert.equal(result.resources.flatMap(r=>r.cues)[0].status,'asr-draft');
 if(process.argv[3]){
  fs.writeFileSync(process.argv[3]+'/draft-test-fixture.json',JSON.stringify({...draftFixture,test_fixture:true},null,2)+'\n',{flag:'wx'});
  fs.writeFileSync(process.argv[3]+'/reviewed-test-fixture.json',JSON.stringify({...reviewedFixture,test_fixture:true},null,2)+'\n',{flag:'wx'});
 }
 console.log('LISTENING REVIEW LOGIC PASS scenes=47 empty_scenes=42 audio=10 initial_reviewed=0 old_checked=reset invalid_timing=rejected explicit_checks=10 text_edit=resets source_evidence=preserved export_catalogue=roundtrip');
})().catch(e=>{console.error(e);process.exitCode=1});
