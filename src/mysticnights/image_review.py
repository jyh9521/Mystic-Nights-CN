"""Publish offline source/final-ISO image pairs with stable, versioned feedback IDs.

No generative service, game launch, font rendering, or image retouching occurs
here. PNGs are decoded from verified disc members, not authoring previews.
"""
from pathlib import Path
import csv
import hashlib
import json

from .artwork import digest, load_graphics_catalogue, apply_artwork
from .graphics import decode_tim2
from .iso9660 import IsoImage
from .resources import parse_res
from .versions import load_version, verify_original


def file_digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(data)
    return h.hexdigest()


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode('utf8')


def script_json(value):
    """Prevent source text from ending an inline JSON script element."""
    return json.dumps(value, ensure_ascii=False).replace('<', '\\u003c').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')


def write_png(image, destination):
    from PIL import Image
    image.save(destination, format='PNG', optimize=False)
    with Image.open(destination) as reopened:
        reopened.load()
        if reopened.convert('RGBA').tobytes() != image.convert('RGBA').tobytes():
            raise ValueError('Published review PNG differs from decoded pixels')
    return {'path': destination.name, 'sha256': file_digest(destination),
            'rgba_sha256': digest(image.convert('RGBA').tobytes()), 'size': destination.stat().st_size}


def read_feedback(path, review):
    """Validate a returned JSON/CSV against stable source IDs, not row numbers."""
    path = Path(path)
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError('Feedback is too large')
    text = path.read_text('utf-8-sig')
    if path.suffix.lower() == '.csv':
        rows = list(csv.DictReader(text.splitlines(keepends=True)))
        rows = [{**r, 'id': r.get('image_id'), 'comment': r.get('feedback')} for r in rows]
    else:
        value = json.loads(text)
        if (value.get('format') != 'disc-image-feedback' or value.get('version') != 1
                or value.get('source_iso_sha256') != review['source_iso_sha256']):
            raise ValueError('Feedback source/format mismatch')
        rows = value['entries']
    known = {i['id']: i for i in review['items']}
    seen = set()
    result = []
    if not isinstance(rows, list) or len(rows) > len(known):
        raise ValueError('Feedback entry count mismatch')
    for row in rows:
        key, status, comment = row.get('id'), row.get('status'), row.get('comment')
        if (key not in known or key in seen or status not in ('unreviewed', 'ok', 'issue')
                or not isinstance(comment, str) or len(comment) > 50000):
            raise ValueError('Unknown/duplicate/malformed feedback entry')
        seen.add(key)
        item = known[key]
        if row.get('source_sha256') != item['source_sha256']:
            raise ValueError('Feedback image source mismatch')
        localized = row.get('localized_sha256', '')
        if len(localized) != 64 or any(c not in '0123456789abcdef' for c in localized):
            raise ValueError('Feedback translated hash is invalid')
        if not comment.strip() and status == 'unreviewed':
            continue
        stale = localized != item['localized_sha256']
        result.append({'id': key, 'number': item['number'], 'references': item['references'],
                       'source_sha256': item['source_sha256'], 'feedback_localized_sha256': localized,
                       'current_localized_sha256': item['localized_sha256'],
                       'stale': stale, 'reported_status': status,
                       'status': 'unreviewed' if stale else status, 'comment': comment})
    return {'format': 'validated-image-feedback', 'version': 1,
            'review_revision': review['revision'], 'feedback_sha256': digest(text.encode('utf8')),
            'entries': result, 'opinion_entries': sum(bool(r['comment'].strip()) or r['status'] == 'issue' for r in result)}


def stable_order(unique, recipe, source_sha256):
    """A retained image must not renumber every later feedback entry."""
    if (recipe.get('format') != 'disc-image-review-order' or recipe.get('version') != 1
            or recipe.get('source_iso_sha256') != source_sha256):
        raise ValueError('Review order source/format mismatch')
    keys = recipe['tim2']
    if len(keys) != len(set(keys)) or set(keys) != set(unique):
        raise ValueError('Review order source inventory mismatch')
    return keys


def attach_previous_feedback(payload, path):
    """Keep old opinions separate from a new round of acceptance/feedback."""
    validated = read_feedback(path, {**payload, 'revision': 'prepublication'})
    by_id = {row['id']: row for row in validated['entries']}
    counts = {'carried_confirmations': 0, 'changed_for_recheck': 0}
    for item in payload['items']:
        row = by_id.get(item['id'])
        if not row:
            continue
        item['previous_feedback'] = {
            'comment': row['comment'], 'status': row['reported_status'],
            'localized_sha256': row['feedback_localized_sha256'], 'changed': row['stale']}
        if row['stale']:
            counts['changed_for_recheck'] += 1
        elif row['reported_status'] == 'ok':
            item['initial_status'] = 'ok'
            counts['carried_confirmations'] += 1
    payload['previous_feedback_summary'] = counts


def build_review(root, original_path, modified_path, manifest_path, locale, output, *, audit_path=None, feedback_path=None):
    from PIL import Image
    root = Path(root).resolve()
    output = Path(output).resolve()
    if output.exists() or not output.is_relative_to(root / 'build'):
        raise ValueError('Review output must be new and under the project build directory')
    original = verify_original(Path(original_path), load_version(root / 'assets/game-version.json'))
    manifest = json.loads(Path(manifest_path).read_text('utf8'))
    if (file_digest(original_path) != manifest['original']['sha256']
            or file_digest(modified_path) != manifest['modified']['sha256']):
        raise ValueError('Review ISO/manifest identity mismatch')
    modified = IsoImage(Path(modified_path))
    source_review = json.loads((root / 'assets/graphics-source-review.json').read_text('utf8'))
    dispositions = {t['sha256']: t for t in source_review['textures']}
    slots = json.loads((root / 'assets/graphics-text-slots.json').read_text('utf8'))
    registered = {t['sha256']: t for t in slots['textures']}
    catalogue = load_graphics_catalogue(root / 'locales' / locale / 'graphics.json')
    patches = {p['source_sha256']: p for p in catalogue['artwork_patches']}
    targets = {e['id']: e['target'] for e in catalogue['entries']}
    audit = json.loads(Path(audit_path).read_text('utf8')) if audit_path else {'textures': []}
    audit_by = {t['source_sha256']: t for t in audit['textures'] + audit.get('restored_images', [])}
    unique = {}
    refs = 0
    resources = 0
    for name in sorted(original.files):
        if not name.endswith('.RES'):
            continue
        before = parse_res(original.read(name))
        after = parse_res(modified.read(name))
        resources += 1
        if [e.name for e in before.entries] != [e.name for e in after.entries]:
            raise ValueError('Review archive member order mismatch')
        for entry, new_entry in zip(before.entries, after.entries):
            if not entry.name.endswith('.TM2'):
                continue
            data, changed = before.read(entry), after.read(new_entry)
            key = digest(data)
            if key not in dispositions:
                raise ValueError('Unclassified source texture')
            if key in patches:
                if apply_artwork(data, patches[key]) != changed:
                    raise ValueError('Final ISO artwork differs from locale recipe')
            elif dispositions[key]['disposition'] != 'runtime-font-atlas' and data != changed:
                raise ValueError('Unregistered changed texture')
            if key in unique and unique[key]['after'] != changed:
                raise ValueError('Physical aliases have different translated payloads')
            row = unique.setdefault(key, {'before': data, 'after': changed, 'references': []})
            row['references'].append({'resource': name, 'member': entry.name})
            refs += 1
    if set(unique) != set(dispositions):
        raise ValueError('Source inventory is not closed')
    output.mkdir(parents=True)
    (output / 'images').mkdir()
    items = []
    files = []

    def publish(key, row, source_image, translated_image, texts, kind, disposition, note, fixed=False):
        number = len(items) + 1
        stem = f'{number:04d}'
        a = output / 'images' / (stem + '-original.png')
        b = output / 'images' / (stem + '-localized.png')
        files.append({'path': 'images/' + a.name, **{k: v for k, v in write_png(source_image, a).items() if k != 'path'}})
        if row['before'] == row['after']:
            b = a
        else:
            files.append({'path': 'images/' + b.name, **{k: v for k, v in write_png(translated_image, b).items() if k != 'path'}})
        items.append({'number': number, 'id': kind + ':' + key, 'kind': kind,
                      'source_sha256': key, 'localized_sha256': digest(row['after']),
                      'width': source_image.width, 'height': source_image.height,
                      'original_image': 'images/' + a.name, 'chinese_image': 'images/' + b.name,
                      'references': row['references'], 'texts': texts, 'disposition': disposition,
                      'localized': bool(texts), 'restored': disposition == 'retain-original-user-request',
                      'changed': row['before'] != row['after'],
                      'fixed': fixed, 'review_note': note})

    # Translated images first; every remaining source TIM2 is also reviewable.
    order = stable_order(unique, json.loads((root / 'assets/image-review-order.json').read_text('utf8')),
                         manifest['original']['sha256'])
    for key in order:
        row = unique[key]
        before, profile = decode_tim2(row['before'])
        after, new_profile = decode_tim2(row['after'])
        if profile != new_profile:
            raise ValueError('Review texture geometry/format changed')
        text_rows = [{'id': s['id'], 'source': s['source'], 'target': targets.get(s['id'], ''), 'rect': s['rect']}
                     for s in registered.get(key, {}).get('slots', []) if s.get('install')]
        record = audit_by.get(key)
        if record and record['localized_sha256'] != digest(row['after']):
            raise ValueError('Artwork inspection record is stale')
        note = record['note'] if record else (
            '运行时字体图集，不作为单幅菜单图；字码对应关系见字体验证。' if dispositions[key]['disposition'] == 'runtime-font-atlas'
            else '保留原图：无可靠可译正文、技术标识或模糊微字。未填写意见不代表已认可。')
        publish(key, row, before, after, text_rows, 'tim2', dispositions[key]['disposition'], note,
                bool(record and record['result'] == 'fixed'))

    raw = json.loads((root / 'assets/raw-image-slots.json').read_text('utf8'))
    raw_catalogue = json.loads((root / 'locales' / locale / 'raw-images.json').read_text('utf8'))
    raw_targets = {r['id']: r['target'] for r in raw_catalogue['entries']}
    for recipe in raw['images']:
        name = recipe['resource']
        data, changed = original.read(name), modified.read(name)
        w, h, channels = recipe['profile']
        if channels != 3 or len(data) != w * h * 3 or digest(data) != recipe['sha256']:
            raise ValueError('Raw image source profile mismatch')
        publish(digest(data), {'before': data, 'after': changed, 'references': [{'resource': name, 'member': ''}]},
                Image.frombytes('RGB', (w, h), data).convert('RGBA'),
                Image.frombytes('RGB', (w, h), changed).convert('RGBA'),
                [{'id': s['id'], 'source': s['source'], 'target': raw_targets[s['id']], 'rect': s['rect']} for s in recipe['slots']],
                'rgb24', 'authored-pixel-delta', '无头 RGB24 原图与最终 ISO 回读；不是 TIM2。')
    # UI defaults to the 194 localized artworks, with all 1141 carriers available.
    payload = {'format': 'disc-image-review', 'version': 1, 'locale': locale,
               'source_iso_sha256': manifest['original']['sha256'],
               'localized_iso_sha256': manifest['modified']['sha256'],
               'resources': resources, 'physical_tim2_members': refs,
               'unique_tim2': len(unique), 'localized_artworks': sum(i['localized'] for i in items),
               'items': items}
    if feedback_path:
        attach_previous_feedback(payload, feedback_path)
    payload['revision'] = digest(canonical(payload))
    template = root / 'tools/review_page'
    html = (template / 'review.html').read_text('utf8').replace('__DATA__', script_json(payload))
    html = html.replace('__CORE__', (template / 'feedback.js').read_text('utf8'))
    html = html.replace('__SCRIPT__', (template / 'review.js').read_text('utf8'))
    (output / 'index.html').write_text(html, 'utf8', newline='\n')
    (output / 'manifest.json').write_bytes(canonical({**payload, 'png_files': files}))
    (output / '打开筛查网页.cmd').write_bytes(b'@echo off\r\nstart "" "%~dp0index.html"\r\n')
    (output / '使用说明.txt').write_text(
        '双击 index.html 或 打开筛查网页.cmd，无需启动游戏或联网。\n'
        '左原图、右最终 ISO 原生汉化图；默认显示全部已汉化图片，可切换查看全部源图。\n'
        '左右键直接翻页（输入框内同样有效），翻页前自动保存意见。输入法组词时不抢按键。\n'
        '未看/认可/需修改分别记录，空白意见不视为认可。反馈仅保存在本机浏览器。\n'
        '请点击导出意见 JSON，将导出的文件发回；CSV 也可阅读。支持重新导入 JSON。\n'
        '不同 ISO 版本的意见导入后保留文字，但会标注旧版本，认可状态重置为待看。\n'
        '网页图片用于离线筛查，不是游戏截图，不包含模拟器高清替换后的实际渲染。\n', 'utf8')
    if (output / 'index.html').read_text('utf8') != html:
        raise ValueError('Review HTML reopening mismatch')
    if json.loads((output / 'manifest.json').read_text('utf8'))['revision'] != payload['revision']:
        raise ValueError('Review manifest reopening mismatch')
    return {'images': len(items), 'localized': payload['localized_artworks'], 'png_files': len(files),
            'physical_tim2_members': refs, 'revision': payload['revision'], 'output': str(output / 'index.html')}
