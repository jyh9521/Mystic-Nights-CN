const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
const hash = c => c.repeat(64);
const items = [1,2,3].map(n => ({number:n,id:'tim2:'+hash(String(n)),source_sha256:hash(String(n)),localized_sha256:hash('a'),
  width:256,height:256,original_image:`images/${n}-original.png`,chinese_image:`images/${n}-localized.png`,
  references:[{resource:'RES/UI/A.RES',member:`U${n}.TM2`}],texts:[{source:'OK',target:'确定'}],localized:n<3,changed:n<3,fixed:n===2,review_note:'离线对照'}));
const data = {format:'disc-image-review',revision:'fixture-r1',source_iso_sha256:hash('d'),localized_iso_sha256:hash('e'),items};
const memory = new Map();
function setup(brokenStorage=false) {
  const elements=new Map(), callbacks={}, downloads=[], blobs=[];
  function element(id) {
    const attrs={}, events={}, classes=new Set();
    return {id,value:'',textContent:'',disabled:false,dataset:{},style:{},clientWidth:650,clientHeight:400,files:[],
      classList:{toggle(c,force){if(force===undefined)force=!classes.has(c);if(force)classes.add(c);else classes.delete(c);},contains(c){return classes.has(c);},add(c){classes.add(c);},remove(c){classes.delete(c);}},
      addEventListener(k,f){events[k]=f;},events,focus(){},removeAttribute(k){delete this[k];delete attrs[k];},
      click(){if(this.onclick)return this.onclick();if(id==='anchor')downloads.push({name:this.download,href:this.href});}};
  }
  const $=id=>{if(!elements.has(id))elements.set(id,element(id));return elements.get(id);};
  $('review-data').textContent=JSON.stringify(data);
  const groups={};
  for(const [attr,values]of Object.entries({filter:['localized','all','unreviewed','issue','fixed','retained'],status:['unreviewed','ok','issue'],zoom:['fit','1','2','4'],bg:['checker','navy','black','light']})) {
    groups[`[data-${attr}]`]=values.map(v=>{const e=element(attr+'-'+v);e.dataset[attr]=v;return e;});
  }
  groups['.imagebox']=[$('original-box'),$('localized-box')];
  const context=vm.createContext({console,Blob,Map,Set,JSON,Number,String,Math,Error,
    localStorage:{getItem(k){if(brokenStorage)throw Error('disabled');return memory.get(k)||null;},setItem(k,v){if(brokenStorage)throw Error('disabled');memory.set(k,v);}},
    document:{getElementById:$,querySelectorAll:q=>groups[q]||[],addEventListener(k,f){callbacks[k]=f;},createElement:()=>element('anchor')},
    window:{addEventListener(k,f){callbacks['window:'+k]=f;}},
    URL:{createObjectURL(b){blobs.push(b);return 'blob:'+blobs.length;},revokeObjectURL(){}},setTimeout(){}});
  vm.runInContext(fs.readFileSync('tools/review_page/feedback.js','utf8'),context);
  vm.runInContext(fs.readFileSync('tools/review_page/review.js','utf8'),context);
  return {$,groups,callbacks,downloads,blobs,context,eval:s=>vm.runInContext(s,context)};
}
(async()=>{
  let t=setup();assert.match(t.$('count').textContent,/1 \/ 2/);assert.equal(t.$('original').src,'images/1-original.png');
  t.$('comment').value='背景有残留，含"引号"\n第二行';t.$('comment').events.input();
  let prevented=false;t.callbacks.keydown({key:'ArrowRight',preventDefault(){prevented=true;},stopImmediatePropagation(){}});
  assert.ok(prevented);assert.equal(t.eval('current.number'),2);assert.equal(t.$('comment').value,'');
  t.$('prev').click();assert.match(t.$('comment').value,/第二行/);
  t.callbacks.keydown({key:'ArrowRight',isComposing:true});assert.equal(t.eval('current.number'),1);
  t.groups['[data-status]'].find(e=>e.dataset.status==='issue').click();
  t.$('export-json').click();const exported=JSON.parse(await t.blobs.at(-1).text());assert.equal(exported.entries.length,1);assert.equal(exported.entries[0].status,'issue');
  t.$('export-csv').click();assert.match(await t.blobs.at(-1).text(),/""引号""/);assert.ok(t.downloads.at(-1).name.endsWith('.csv'));
  t=setup();assert.match(t.$('comment').value,/第二行/); // Reload persistence.
  t.$('search').value='not-existing';t.$('search').events.input();assert.equal(t.$('count').textContent,'0 / 0');assert.equal(t.$('original').src,undefined);assert.equal(t.$('original-link').href,undefined);assert.ok(t.$('comment').disabled);
  t.$('search').value='';t.$('search').events.input();
  t.groups['[data-filter]'].find(e=>e.dataset.filter==='fixed').click();assert.equal(t.eval('current.number'),2);
  t.groups['[data-filter]'].find(e=>e.dataset.filter==='all').click();assert.match(t.$('count').textContent,/1 \/ 3/);
  t.$('jump').value='3';t.$('go').click();assert.equal(t.eval('current.number'),3);
  t.groups['[data-filter]'].find(e=>e.dataset.filter==='retained').click();assert.equal(t.eval('current.number'),3);
  const old=structuredClone(exported);old.entries[0].localized_sha256=hash('f');old.entries[0].status='ok';
  const input=t.$('import-file');input.files=[{size:100,text:async()=>JSON.stringify(old)}];await input.events.change({target:input});
  assert.equal(t.eval(`notes.get(${JSON.stringify(items[0].id)}).status`),'unreviewed');
  assert.equal(t.eval(`notes.get(${JSON.stringify(items[0].id)}).previous_localized_sha256`),hash('f'));
  const bad=structuredClone(exported);bad.entries[0].id='unknown';input.files=[{size:100,text:async()=>JSON.stringify(bad)}];
  const before=t.eval('JSON.stringify([...notes])');await input.events.change({target:input});assert.match(t.$('error').textContent,/导入未生效/);assert.equal(t.eval('JSON.stringify([...notes])'),before);
  const b=setup(true);b.$('comment').value='存储禁用仍可导出';b.$('comment').events.input();b.$('export-json').click();assert.equal(JSON.parse(await b.blobs[0].text()).entries[0].comment,'存储禁用仍可导出');
  memory.clear();items[0].initial_status='ok';items[1].previous_feedback={comment:'旧意见：背景残留',status:'issue',changed:true};items[2].restored=true;
  const seeded=setup();assert.match(seeded.$('count').textContent,/1 \/ 3/);assert.equal(seeded.eval('notes.get(items[0].id).status'),'ok');
  seeded.$('next').click();assert.match(seeded.$('previous-opinion').textContent,/旧意见：背景残留/);assert.equal(seeded.$('comment').value,'');assert.equal(seeded.eval('notes.get(current.id).status'),'unreviewed');
  seeded.$('export-json').click();const recheck=JSON.parse(await seeded.blobs.at(-1).text());assert.equal(recheck.entries.length,1);assert.equal(recheck.entries[0].status,'ok');
  seeded.$('search').value='missing-again';seeded.$('search').events.input();assert.equal(seeded.$('previous-opinion').textContent,'');
  console.log('REVIEW NAVIGATION PASS arrows-in-input IME search empty-state jump filters autosave reload JSON/CSV downloads import stale-reset atomic-rejection storage-failure=pass');
  console.log('REVIEW HISTORY PASS unchanged-approval carried changed-opinion readonly new-comment empty restored-image reviewable old-opinion not-reexported=pass');
})().catch(e=>{console.error(e);process.exitCode=1;});
