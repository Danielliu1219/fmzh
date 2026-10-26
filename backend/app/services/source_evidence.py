"""从当前账号/科目资料中校验引用，只展示可由原文偏移复核的片段。"""
import hashlib
import json

from ..schemas.schemas import SourceReference

MAX_REFERENCES = 3


def content_hash(text):
    return hashlib.sha256((text or '').encode('utf-8')).hexdigest()


def _find(text, query):
    query = query.strip()
    if len(query) < 2:
        return None
    index = text.find(query)
    if index >= 0:
        return index, index + len(query)
    # PDF 常在词句中折行，只忽略空白，不折叠数学符号或改写文字。
    compact, positions = [], []
    for index, character in enumerate(text):
        if not character.isspace():
            compact.append(character); positions.append(index)
    needle = ''.join(character for character in query if not character.isspace())
    if len(needle) < 2:
        return None
    index = ''.join(compact).find(needle)
    return (positions[index], positions[index + len(needle) - 1] + 1) if index >= 0 else None


def item_title(item):
    return getattr(item, 'name', None) or getattr(item, 'content', None) or getattr(item, 'type', '')


def _reference(material, span, match):
    start, end = span
    # 限制单条引用体积；这里保存的片段永远直接取自资料，不沿用模型编造的文字。
    end = min(end, start + 800)
    return SourceReference(material_id=material.id, quote=material.text_content[start:end],
                           start=start, end=end, content_hash=content_hash(material.text_content), match=match,
                           material_created_at=material.created_at)


def references_for(item, materials):
    available = {material.id: material for material in materials if material.parse_status == 'done' and material.text_content}
    references, seen = [], set()
    for proposed in item.citations[:MAX_REFERENCES]:
        material = available.get(proposed.material_id)
        span = _find(material.text_content, proposed.quote) if material and len(proposed.quote.strip()) >= 6 else None
        if span and (material.id, span) not in seen:
            references.append(_reference(material, span, 'quote'))
            seen.add((material.id, span))
    if references:
        return references
    # 旧结果和未提供有效引文的模型结果仅做保守关键词定位，明确不把它冒称为模型引证。
    keyword = item_title(item)
    for material in sorted(available.values(), key=lambda row: (row.source_type != item.source, row.id)):
        span = _find(material.text_content, keyword)
        if span:
            references.append(_reference(material, span, 'keyword'))
        if len(references) >= MAX_REFERENCES:
            break
    return references


def attach_references(result, materials):
    for item in [*result.knowledge_points, *result.exam_focus, *result.question_types]:
        item.citations = references_for(item, materials)


def location_for(material, start, end):
    try:
        parts = json.loads(material.text_locations or '[]')
    except (ValueError, TypeError):
        parts = []
    matched = []
    if isinstance(parts, list):
        for part in parts:
            if (isinstance(part, dict) and type(part.get('start')) is int and type(part.get('end')) is int
                    and 0 <= part['start'] < part['end'] <= len(material.text_content)
                    and part['start'] < end and part['end'] > start):
                matched.append(part)
    if matched:
        first, last = matched[0], matched[-1]
        label = str(first.get('label', '原文片段'))
        if first is not last:
            label += ' 至 ' + str(last.get('label', '原文片段'))
        page = first.get('number') if first.get('kind') == 'page' else None
        return label, page
    return f'解析文本第 {start + 1}～{end} 字（旧资料未保存页码）', None


def excerpt_for(material, reference):
    base = dict(material_id=reference.material_id, match=reference.match)
    if material is None or material.parse_status != 'done':
        return dict(**base, status='unavailable', note='原引用资料已删除、移出当前科目或无法解析，请重新生成分析。')
    base.update(material_title=material.title, source_type=material.source_type, file_type=material.file_type)
    if reference.material_created_at is None or reference.material_created_at != material.created_at:
        return dict(**base, status='unavailable', note='原引用资料已被替换，请重新生成分析。')
    text = material.text_content or ''
    if not reference.content_hash or reference.content_hash != content_hash(text):
        return dict(**base, status='changed', note='资料内容已变化，旧引用已失效，请重新生成分析。')
    start, end = reference.start, reference.end
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text) or text[start:end] != reference.quote:
        return dict(**base, status='changed', note='原文定位已失效，请重新生成分析。')
    left, right = max(0, start - 160), min(len(text), end + 240)
    location, page = location_for(material, start, end)
    return dict(**base, status='available', location=location, page=page, start=start, end=end, material_created_at=material.created_at,
                content_hash=reference.content_hash, context=text[left:right], highlight_start=start-left,
                highlight_end=end-left, note='已核对引用文字与当前资料一致。' if reference.match == 'quote'
                else '按关键词匹配的原文片段，供核对推荐；不代表已核实出现次数或必考结论。')
