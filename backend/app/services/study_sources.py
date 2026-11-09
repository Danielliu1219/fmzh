"""本地建立可复核的题目/课件索引；不调用模型，不修改原始解析文本。"""
import json
import re

from .source_evidence import content_hash, location_for, references_for

QUESTION = re.compile(r'(?m)^[ \t]*(?P<label>第[一二三四五六七八九十百\d]{1,6}题|\d{1,3}[、．.]|[一二三四五六七八九十]{1,3}[、．.])(?!\d)[ \t]*')
SECTION = re.compile(r'^(?P<number>[一二三四五六七八九十]{1,3})[、．.]\s*(?P<kind>选择|填空|计算|证明|解答|综合|判断|简答|应用)题?')
ANSWER = re.compile(r'(?m)^[ \t]*(?:【(?:参考)?答案】|(?:参考)?答案\s*[:：]|解析\s*[:：]|解\s*[:：])')


def clean_display(text):
    # 仅清理显示用控制符；不猜测/改写公式，不用清洗后的偏移访问原文件。
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text).replace('\u00a0', ' ')


def _locations(material):
    try:
        data = json.loads(material.text_locations or '[]')
    except (ValueError, TypeError):
        return []
    return [p for p in data if isinstance(p, dict) and type(p.get('start')) is int
            and type(p.get('end')) is int and 0 <= p['start'] < p['end'] <= len(material.text_content or '')] if isinstance(data, list) else []


def material_units(material):
    text = material.text_content or ''
    if material.parse_status != 'done' or not text.strip():
        return []
    revision = content_hash(text)
    identity = content_hash(f'{material.id}:{material.created_at}:{revision}')[:20]
    parts = _locations(material)
    is_exam = material.source_type in ('历年题', '练习题', '平时作业') or bool(re.search(r'试卷|试题|习题', material.title))
    units = []

    def add(start, end, kind, question='', section=''):
        while start < end and text[start].isspace(): start += 1
        while end > start and text[end-1].isspace(): end -= 1
        if start >= end: return
        location, _ = location_for(material, start, end)
        matched = [p for p in parts if p['start'] < end and p['end'] > start]
        pages = list(dict.fromkeys(p['number'] for p in matched if p.get('kind') == 'page' and type(p.get('number')) is int))
        question_label = question if not question or question.endswith('题') else f'第 {question} 题'
        subquestions = list(dict.fromkeys(re.findall(r'(?m)(?:^|\s)[（(](\d{1,2})[）)]', text[start:end])))
        subquestion_label = '含小问 ' + '、'.join(f'（{number}）' for number in subquestions) if subquestions else ''
        label = ' · '.join(filter(None, (section, question_label, subquestion_label, location)))
        if is_exam and kind == 'reading':
            label += ' · 题号待核对'
        units.append(dict(id=f'm{material.id}-{identity}-{start}-{end}', material_id=material.id,
            material_title=material.title, source_type=material.source_type, file_type=material.file_type,
            exam_id=material.exam_id, revision=revision, start=start, end=end,
            kind=kind, question_number=question, location=location, label=label, pages=pages,
            text=clean_display(text[start:end]), subquestions=subquestions,
            recognition='按题号识别，可能包含同页相邻内容，请核对原页。' if kind == 'question' else '按原文页、幻灯片或段落定位。'))

    if is_exam:
        marks = list(QUESTION.finditer(text))
        section = ''
        # 每个编号范围保留到下一个大题/题型标题；(1)(2)不拆走共同题干。
        for index, match in enumerate(marks):
            end = marks[index+1].start() if index+1 < len(marks) else len(text)
            section_match = SECTION.match(text[match.start():end].lstrip())
            if section_match:
                section = f"第{section_match['number']}大题 · {section_match['kind']}题"
                # 大题下面直接列小问时，保留共同题干和整个大题。
                if text[match.end():end].partition('\n')[2].strip():
                    add(match.start(), end, 'question', section=section)
                continue
            add(match.start(), end, 'question', match['label'].rstrip('、．.'), section)
    if not units:
        if parts and material.file_type != 'txt':
            for part in parts:
                add(part['start'], part['end'], 'reading')
        else:
            # 无可靠页码时按真实文本段落定位，绝不推测页码。
            for start in range(0, len(text), 2400):
                add(start, min(start+2400, len(text)), 'reading')
    return units


def display_analysis(result, materials):
    """为旧分析补回可读资料名，仅修改返回副本，保留原始引文和答案。"""
    titles = {str(material.id): material.title for material in materials}

    def replace(match):
        numbers = re.findall(r'\d+', match[0])
        return '、'.join(f'《{titles[number]}》' if number in titles else '已移除的资料' for number in numbers)

    def readable(value):
        return re.sub(r'资料(?:编号)?\s*\d+(?:\s*[、,，]\s*\d+)*(?![\d年\-—–])', replace, value)

    output = result.model_copy(deep=True)
    output.summary = readable(output.summary)
    groups = [(output.knowledge_points, ('recommend_reason', 'source', 'practice_hint')),
              (output.exam_focus, ('content', 'basis', 'source')),
              (output.question_types, ('basis', 'source')),
              (output.review_plan, ('title', 'detail'))]
    for items, fields in groups:
        for item in items:
            for field in fields:
                setattr(item, field, readable(getattr(item, field)))
    units = [unit for material in materials for unit in material_units(material)]
    by_material = {material.id: material for material in materials}
    for point in output.knowledge_points:
        linked = {unit['id'] for unit, _ in linked_units(point, units, materials)}
        matches = set()
        for unit in units:
            material = by_material[unit['material_id']]
            if material.file_type == 'pdf':
                from .pdf_recognition import cached_pages, recognized_unit
                if not unit['pages'] or any(str(page) not in cached_pages(material) for page in unit['pages']):
                    continue
                recognized = recognized_unit(material, unit)
                if recognized['question_identified'] and keyword_match(point.name, recognized['text']):
                    matches.add((material.id, tuple(recognized['pages']), recognized['input_hash']))
            elif unit['id'] in linked or keyword_match(point.name, unit['text']):
                matches.add((material.id, unit['id']))
        point.occurrence_count = len(matches) if matches else None
        point.occurrence_material_count = len({match[0] for match in matches})
    return output


def build_context(materials, per_material=6000, total_limit=30000, *, with_ids=False):
    """来源ID和正文同次输入分析；上下文截断不产生虚构可选题目。"""
    output, used, included = [], 0, set()
    for material in materials:
        local = 0
        chunks = []
        for unit in material_units(material):
            header = f"\n【来源ID {unit['id']}｜{unit['label']}】\n"
            remaining = min(per_material-local, total_limit-used) - len(header)
            if remaining < 80: break
            body = unit['text'][:remaining]
            chunk = header + body
            chunks.append(chunk); local += len(chunk); used += len(chunk)
            included.add(unit['id'])
        if chunks:
            weight = material.weight
            output.append(f'【资料编号 {material.id}｜{material.title}】[{material.source_type}｜资料权重 {weight if weight is not None else "默认"}]' + ''.join(chunks))
        if used >= total_limit-80: break
    context = '\n\n'.join(output)
    return (context, included) if with_ids else context


def keyword_match(name, body):
    compact = ''.join(body.split()).casefold()
    phrases = [name, re.split(r'[（(]', name)[0]]
    phrases += re.split(r'[、与和/]', phrases[-1])
    phrases += [re.sub(r'(?:计算|应用|的概念|与方法|方法)$', '', p) for p in phrases[:]]
    return any(2 <= len(p.strip()) <= 80 and p.strip() not in ('计算','应用','函数','知识点','核心概念','综合','基础')
               and (re.search(r'(?<!不)' + re.escape(''.join(p.split()).casefold()), compact)
                    if p.strip().startswith('定积分') else ''.join(p.split()).casefold() in compact) for p in phrases)


def linked_units(item, units, materials):
    by_id = {u['id']: u for u in units}
    selected = [by_id[s] for s in getattr(item, 'source_ids', []) if s in by_id]
    if selected:
        return [(u, 'model') for u in selected]
    citations = references_for(item, materials)
    quoted = [(u, 'quote') for u in units if any(c.match == 'quote' and c.material_id == u['material_id']
        and c.start < u['end'] and c.end > u['start'] for c in citations)]
    if quoted: return quoted
    name = getattr(item, 'name', '') or getattr(item, 'knowledge_point', '')
    return [(u, 'keyword') for u in units if name and keyword_match(name, u['text'])]


def attach_study_sources(result, materials):
    # 只接受同次输入中真正出现过的ID，不能关联被上下文裁剪掉的材料。
    _, valid = build_context(materials, with_ids=True)
    for item in [*result.knowledge_points, *result.review_plan]:
        # 模型只选择可复核ID；局部匹配保持在读取端并显式标注，不能冒充模型确认。
        item.source_ids = list(dict.fromkeys(s for s in item.source_ids if s in valid))[:8]


def library(materials, result=None):
    units = [u for m in materials for u in material_units(m)]
    from .pdf_recognition import cached_pages, recognized_unit
    by_material = {material.id: material for material in materials}
    for unit in units:
        material = by_material[unit['material_id']]
        if material.file_type == 'pdf' and unit['pages'] and all(str(page) in cached_pages(material) for page in unit['pages']):
            recognized = recognized_unit(material, unit)
            for field in ('text', 'label', 'location', 'pages', 'subquestions', 'recognition'):
                unit[field] = recognized[field]
    links = {u['id']: [] for u in units}
    if result:
        for point in result.knowledge_points:
            for unit, method in linked_units(point, units, materials):
                links[unit['id']].append(dict(name=point.name, method=method))
        for plan in result.review_plan:
            for source_id in plan.source_ids:
                if source_id in links and plan.knowledge_point:
                    link = dict(name=plan.knowledge_point, method='model')
                    if link not in links[source_id]: links[source_id].append(link)
    return [{**{k: v for k, v in u.items() if k != 'text'}, 'preview': u['text'][:100], 'knowledge_points': links[u['id']]} for u in units]


def unit_detail(unit):
    answer = ANSWER.search(unit['text']) if unit['kind'] == 'question' else None
    return {**unit, 'question_text': unit['text'][:answer.start()].strip() if answer else unit['text'],
            'original_answer': unit['text'][answer.start():] if answer else '',
            'answer_note': '仅显示同一片段中明确标注的答案；其他页的答案请在原文件核对。',
            'steps': ['先遮住答案，阅读原题或课件原文，写下已知条件/核心定义。',
                      '独立作答或合上课件复述，再展开答案核对关键步骤。',
                      '不会的内容标记到错题本，后续集中回顾。']}
