const assert = require('node:assert/strict');
const core = require('../tools/review_page/feedback.js');
const item = {id:'tim2:'+'a'.repeat(64),number:1,source_sha256:'a'.repeat(64),localized_sha256:'b'.repeat(64),references:[{resource:'RES/A.RES',member:'A.TM2'}]};
const data={revision:'r1',source_iso_sha256:'c'.repeat(64),localized_iso_sha256:'d'.repeat(64),items:[item]};
const notes=new Map([[item.id,{comment:'引号"、逗号,\n中文意见 </script>',status:'issue'}]]);
const value=core.exportJSON(data,notes);
assert.equal(value.entries.length,1);
assert.equal(core.importJSON(JSON.parse(JSON.stringify(value)),data)[0].comment,notes.get(item.id).comment);
assert.equal(core.importJSON(value,data)[0].status,'issue');
const old=structuredClone(value);old.entries[0].localized_sha256='e'.repeat(64);old.entries[0].status='ok';
const stale=core.importJSON(old,data)[0];assert.equal(stale.status,'unreviewed');assert.equal(stale.previous_localized_sha256,'e'.repeat(64));
const duplicate=structuredClone(value);duplicate.entries.push(duplicate.entries[0]);assert.throws(()=>core.importJSON(duplicate,data));
const unknown=structuredClone(value);unknown.entries[0].id='bad';assert.throws(()=>core.importJSON(unknown,data));
const source=structuredClone(value);source.source_iso_sha256='0'.repeat(64);assert.throws(()=>core.importJSON(source,data));
const badStatus=structuredClone(value);badStatus.entries[0].status='approved-by-default';assert.throws(()=>core.importJSON(badStatus,data));
assert.equal(core.exportJSON(data,new Map()).entries.length,0); // Blank is not approval.
assert.match(core.csv(data,notes),/引号""、逗号,/);assert.ok(core.csv(data,notes).startsWith('\uFEFF'));
assert.equal(core.exportJSON(data,new Map([[item.id,{comment:'',status:'ok'}]])).entries.length,1);
console.log('REVIEW FEEDBACK PASS same-version roundtrip old-version reset duplicate/unknown/source rejection CSV quoting blank-not-approval=pass');
