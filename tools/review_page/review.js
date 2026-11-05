/* File:// compatible: embedded data/scripts, local PNGs, no fetch/server. */
'use strict';
const data = JSON.parse(document.getElementById('review-data').textContent);
const $ = id => document.getElementById(id), items = data.items, notes = new Map();
const namespace = 'disc-image-review:' + data.revision + ':';
let persistent = true, order = [], pos = 0, current = null, filterKind = 'localized', zoom = 'fit';
for (const item of items) {
  let note = {comment: '', status: 'unreviewed'};
  try { const value = JSON.parse(localStorage.getItem(namespace + item.id) || 'null'); if (value && typeof value.comment === 'string' && ['unreviewed', 'ok', 'issue'].includes(value.status)) note = value; }
  catch { persistent = false; }
  notes.set(item.id, note);
}
function save() {
  if (!current) return;
  const old = notes.get(current.id), next = {...old, comment: $('comment').value};
  notes.set(current.id, next);
  try { localStorage.setItem(namespace + current.id, JSON.stringify(next)); } catch { persistent = false; }
  $('saved').textContent = persistent ? '意见已自动保存到本机' : '仅保存在当前页面，请导出意见文件留存';
  progress();
}
function progress() {
  const seen = items.filter(i => notes.get(i.id).status !== 'unreviewed').length;
  const count = items.filter(i => notes.get(i.id).comment.trim() || notes.get(i.id).status === 'issue').length;
  $('progress').textContent = `全部 ${items.length} 张 · 已确认 ${seen} · 有意见 ${count}`;
}
function resize() {
  if (!current) return;
  const available = Math.min($('original-box').clientWidth, $('localized-box').clientWidth) - 20;
  const height = $('original-box').clientHeight - 20;
  const s = zoom === 'fit' ? Math.min(available / current.width, height / current.height, 4) : Number(zoom);
  for (const id of ['original', 'localized']) { $(id).style.width = Math.max(1, Math.floor(current.width * s)) + 'px'; $(id).style.height = Math.max(1, Math.floor(current.height * s)) + 'px'; }
}
function render(focus = true) {
  $('error').textContent = '';
  if (!order.length) {
    current = null; $('name').textContent = '没有匹配图片'; $('count').textContent = '0 / 0';
    $('comment').value = ''; $('comment').disabled = true; $('prev').disabled = $('next').disabled = true;
    for (const id of ['original','localized']) $(id).removeAttribute('src');
    for (const id of ['original-link','localized-link']) $(id).removeAttribute('href');
    $('jump').value = '';
    for (const id of ['meta','note','text-list','refs','stale','saved']) $(id).textContent = '';
    return;
  }
  pos = Math.max(0, Math.min(pos, order.length - 1)); current = items[order[pos]];
  $('comment').disabled = false; $('prev').disabled = $('next').disabled = false;
  $('original').src = $('original-link').href = current.original_image;
  $('localized').src = $('localized-link').href = current.chinese_image;
  $('name').textContent = current.references[0].member || current.references[0].resource;
  $('meta').textContent = `#${current.number} · ${current.width}×${current.height} · ${current.references.length} 处引用 · ${current.id}`;
  $('note').textContent = current.review_note;
  $('count').textContent = `${pos + 1} / ${order.length} · 编号 ${current.number}`;
  $('jump').value = current.number; $('jump').max = items.length;
  $('text-list').textContent = current.texts.map(t => `${t.source} → ${t.target}`).join('\n') || '无可靠可译正文，或运行时字体图集；原像素/标识按清单保留。';
  $('refs').textContent = current.references.map(r => r.resource + (r.member ? ':' + r.member : '')).join('\n');
  $('revision').textContent = `原图 ${current.source_sha256}\n汉化 ${current.localized_sha256}\nISO ${data.localized_iso_sha256}`;
  const n = notes.get(current.id); $('comment').value = n.comment;
  $('stale').textContent = n.previous_localized_sha256 ? '这是旧版图片的意见；文字已保留，请重新确认当前图片。' : '';
  document.querySelectorAll('[data-status]').forEach(b => b.classList.toggle('active', b.dataset.status === n.status));
  $('saved').textContent = persistent ? '填写后自动保存；认可状态需主动选择' : '本机存储不可用，请导出留存';
  resize(); progress();
  if (focus) $('comment').focus({preventScroll: true});
}
function applyFilter() {
  save(); const q = $('search').value.toLowerCase();
  order = items.flatMap((i, n) => {
    const note = notes.get(i.id), hay = [i.id, ...i.references.map(r => r.resource + ':' + r.member), ...i.texts.map(t => t.source + t.target)].join(' ').toLowerCase();
    const selected = filterKind === 'all' || filterKind === 'localized' && i.localized || filterKind === 'unreviewed' && i.localized && note.status === 'unreviewed' || filterKind === 'issue' && (note.comment.trim() || note.status === 'issue') || filterKind === 'fixed' && i.fixed || filterKind === 'retained' && !i.localized;
    return selected && hay.includes(q) ? [n] : [];
  });
  pos = 0; render(false);
}
function move(delta) { save(); if (!order.length) return; pos = (pos + delta + order.length) % order.length; render(true); }
document.addEventListener('keydown', e => { if (e.isComposing || e.keyCode === 229) return; if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return; e.preventDefault(); e.stopImmediatePropagation(); move(e.key === 'ArrowLeft' ? -1 : 1); }, {capture:true});
$('prev').onclick = () => move(-1); $('next').onclick = () => move(1); $('comment').addEventListener('input', save);
$('go').onclick = () => { const i = order.findIndex(n => items[n].number === Number($('jump').value)); if (i < 0) { $('error').textContent = '该编号不在当前筛选中'; return; } save(); pos = i; render(true); };
$('jump').addEventListener('keydown', e => {if (e.key === 'Enter') $('go').click();});
$('search').addEventListener('input', applyFilter);
document.querySelectorAll('[data-filter]').forEach(b => b.onclick = () => {filterKind = b.dataset.filter; document.querySelectorAll('[data-filter]').forEach(x => x.classList.toggle('active', x === b)); applyFilter(); render(true);});
document.querySelectorAll('[data-status]').forEach(b => b.onclick = () => {if (!current) return; notes.get(current.id).status = b.dataset.status; delete notes.get(current.id).previous_localized_sha256; save(); render(false);});
document.querySelectorAll('[data-zoom]').forEach(b => b.onclick = () => {zoom = b.dataset.zoom; document.querySelectorAll('[data-zoom]').forEach(x => x.classList.toggle('active', x === b)); resize();});
document.querySelectorAll('[data-bg]').forEach(b => b.onclick = () => {document.querySelectorAll('[data-bg]').forEach(x => x.classList.toggle('active', x === b)); document.querySelectorAll('.imagebox').forEach(x => {for (const c of ['navy','black','light']) x.classList.remove(c); if (b.dataset.bg !== 'checker') x.classList.add(b.dataset.bg);});});
$('sampling').onclick = () => {document.querySelectorAll('.imagebox').forEach(x => x.classList.toggle('smooth')); $('sampling').textContent = $('original-box').classList.contains('smooth') ? '平滑显示' : '像素清晰';};
window.addEventListener('resize', resize); window.addEventListener('beforeunload', save);
for (const id of ['original','localized']) $(id).onerror = () => { $('error').textContent = '图片读取失败：请保留 images 文件夹与网页在同一目录'; };
function download(content, type, extension) {
  const url = URL.createObjectURL(new Blob([content], {type})), a = document.createElement('a'); a.href = url;
  a.download = `image-feedback-${data.localized_iso_sha256.slice(0,12)}.${extension}`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1500);
}
$('export-json').onclick = () => {save(); download(JSON.stringify(ReviewFeedback.exportJSON(data, notes), null, 2), 'application/json;charset=utf-8', 'json');};
$('export-csv').onclick = () => {save(); download(ReviewFeedback.csv(data, notes), 'text/csv;charset=utf-8', 'csv');};
$('import').onclick = () => $('import-file').click();
$('import-file').addEventListener('change', async e => {
  const file = e.target.files[0]; if (!file) return;
  try {
    if (file.size > 20*1024*1024) throw Error('意见文件过大');
    const parsed = ReviewFeedback.importJSON(JSON.parse((await file.text()).replace(/^\uFEFF/, '')), data);
    save();
    for (const row of parsed) { notes.set(row.id, {comment: row.comment, status: row.status, ...(row.previous_localized_sha256 ? {previous_localized_sha256: row.previous_localized_sha256} : {})}); try {localStorage.setItem(namespace + row.id, JSON.stringify(notes.get(row.id)));} catch {persistent = false;} }
    render(false); $('saved').textContent = `已导入 ${parsed.length} 条意见；旧版图片意见保留文字并重置确认状态`;
  } catch (error) {$('error').textContent = '导入未生效：' + error.message;}
  e.target.value = '';
});
applyFilter(); render(false);
