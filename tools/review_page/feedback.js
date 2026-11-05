/* Pure feedback interchange; imported opinions are data, never HTML or code. */
(function (root) {
  'use strict';
  const statuses = ['unreviewed', 'ok', 'issue'];
  function validate(row) {
    if (!row || typeof row.id !== 'string' || typeof row.comment !== 'string' || row.comment.length > 50000 || !statuses.includes(row.status)) throw Error('意见条目格式错误');
  }
  function exportJSON(data, notes) {
    return {format: 'disc-image-feedback', version: 1, revision: data.revision,
      source_iso_sha256: data.source_iso_sha256, localized_iso_sha256: data.localized_iso_sha256,
      entries: data.items.flatMap(item => {
        const n = notes.get(item.id) || {comment: '', status: 'unreviewed'};
        validate({id: item.id, ...n});
        return n.comment.trim() || n.status !== 'unreviewed' ? [{id: item.id, number: item.number,
          source_sha256: item.source_sha256, localized_sha256: item.localized_sha256,
          references: item.references, comment: n.comment, status: n.status,
          ...(n.previous_localized_sha256 ? {previous_localized_sha256: n.previous_localized_sha256} : {})}] : [];
      })};
  }
  function importJSON(value, data) {
    if (value.format !== 'disc-image-feedback' || value.version !== 1 || value.source_iso_sha256 !== data.source_iso_sha256 || !Array.isArray(value.entries) || value.entries.length > data.items.length) throw Error('意见文件不属于此原盘或格式错误');
    const known = new Map(data.items.map(i => [i.id, i])), seen = new Set(), result = [];
    for (const row of value.entries) {
      validate(row);
      const item = known.get(row.id);
      if (!item || seen.has(row.id) || item.source_sha256 !== row.source_sha256 || !/^[0-9a-f]{64}$/.test(row.localized_sha256)) throw Error('意见含未知/重复 ID 或来源不一致');
      seen.add(row.id);
      const stale = row.localized_sha256 !== item.localized_sha256;
      result.push({id: row.id, comment: row.comment, status: stale ? 'unreviewed' : row.status,
        ...(stale ? {previous_localized_sha256: row.localized_sha256} : {})});
    }
    return result; // All rows are validated before the caller mutates any state.
  }
  function csv(data, notes) {
    const rows = [['number', 'image_id', 'source_sha256', 'localized_sha256', 'status', 'feedback'],
      ...data.items.map(i => {const n = notes.get(i.id) || {status: 'unreviewed', comment: ''}; return [i.number, i.id, i.source_sha256, i.localized_sha256, n.status, n.comment];})];
    return '\uFEFF' + rows.map(r => r.map(v => '"' + String(v).replaceAll('"', '""') + '"').join(',')).join('\r\n');
  }
  const api = {exportJSON, importJSON, csv};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.ReviewFeedback = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
