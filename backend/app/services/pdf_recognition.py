"""本机中文/公式混合识别，按原页缓存，保留旧来源与已付费答案。"""
from functools import lru_cache
import json
import os
from pathlib import Path
import re
from threading import Lock, RLock
from types import SimpleNamespace

from fastapi import HTTPException

from ..config import UPLOAD_DIR
from .deletion import _upload_path
from .source_evidence import content_hash
from .study_sources import material_units

ENGINE_VERSION = 'pix2text-1.1.7-layout-v3'
_recognition_lock = RLock()
PDF_RENDER_LOCK = Lock()


def prepare_model_files(download=True):
    """校验固定版本的必需模型文件，补齐中断下载留下的不完整目录。"""
    default_root = Path(os.environ['APPDATA']) / 'pix2text' if os.name == 'nt' else Path.home() / '.pix2text'
    root = Path(os.environ.get('PIX2TEXT_HOME', str(default_root)))
    manifest = json.loads(Path(__file__).with_name('ocr_models.json').read_text(encoding='utf-8'))
    for name, model in manifest['models'].items():
        directory = root / manifest['version'] / (name + '-onnx')
        missing = [filename for filename, size in model['files'].items()
            if not (directory / filename).is_file() or (directory / filename).stat().st_size != size]
        if not missing:
            continue
        if not download:
            raise RuntimeError(f'公式模型 {name} 缺失或不完整，请运行 prepare_ocr.py 补齐')
        from huggingface_hub import snapshot_download
        endpoints = dict.fromkeys([os.environ.get('HF_ENDPOINT', 'https://huggingface.co'), 'https://hf-mirror.com'])
        for endpoint in endpoints:
            try:
                snapshot_download(repo_id='breezedeus/pix2text-' + name, revision=model['revision'],
                    local_dir=directory, allow_patterns=missing, endpoint=endpoint, token=False, max_workers=2,
                    force_download=any((directory / filename).exists() for filename in missing))
                break
            except Exception as exc:
                failure = exc
        else:
            raise RuntimeError(f'公式模型 {name} 下载未完成，请检查官方源或公开镜像连接') from failure
        if any(not (directory / filename).is_file() or (directory / filename).stat().st_size != size
               for filename, size in model['files'].items()):
            raise RuntimeError(f'公式模型 {name} 文件不完整，请重新运行准备命令')
    return root


@lru_cache(maxsize=1)
def ocr_engine():
    os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY', '1')
    os.environ.setdefault('DO_NOT_TRACK', '1')
    import torch
    from pix2text import TextFormulaOCR
    prepare_model_files()
    torch.set_num_threads(2)
    import onnxruntime
    options = onnxruntime.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    return TextFormulaOCR.from_config(device='cpu', enable_spell_checker=False,
        total_configs={'languages': ('ch_sim', 'en'), 'formula': {'model_backend': 'onnx',
            'more_model_configs': {'session_options': options}}})


def recognize_pdf_pages(path, pages):
    """图片只在内存中传给本机OCR；外部网络仅用于首次下载模型权重。"""
    with _recognition_lock:
        import pypdfium2 as pdfium
        output = {}
        engine = ocr_engine()
        for number in pages:
            with PDF_RENDER_LOCK, pdfium.PdfDocument(str(path)) as document:
                if not 1 <= number <= len(document):
                    raise ValueError('原文件没有指定页')
                page = document[number - 1]
                try:
                    bitmap = page.render(scale=min(3, 2400 / max(page.get_size())))
                    try:
                        picture = bitmap.to_pil().convert('RGB')
                    finally:
                        bitmap.close()
                finally:
                    page.close()
            try:
                blocks = engine.recognize(picture, return_text=False, resized_shape=1280)
                anchors, spans = native_layout(path, number, picture.size)
                text = ordered_page_text(blocks, anchors, spans, picture, engine)
            finally:
                picture.close()
            if not isinstance(text, str) or not text.strip():
                raise ValueError('原页没有识别到文字或公式')
            output[str(number)] = text.strip()
        return output


def native_layout(path, number, size):
    """仅从原PDF获取可复核的题号位置和数学字符框，公式正文仍使用OCR。"""
    import pymupdf
    with pymupdf.open(path) as document:
        page = document[number - 1]
        sx, sy = size[0] / page.rect.width, size[1] / page.rect.height
        spans = []
        anchors = []
        for block in page.get_text('dict')['blocks']:
            for line in block.get('lines', []):
                for span in line['spans']:
                    x0, y0, x1, y1 = span['bbox']
                    item = {'text': span['text'], 'font': span['font'], 'box': (x0*sx, y0*sy, x1*sx, y1*sy)}
                    spans.append(item)
                    match = re.fullmatch(r'(\d{1,3})[.．、]\s*', span['text'])
                    if match and x0 < page.rect.width * .25:
                        anchors.append({**item, 'number': match[1], 'kind': 'question'})
        return sorted(anchors, key=lambda item: item['box'][1]), spans


def block_box(block):
    points = block['position']
    return min(float(p[0]) for p in points), min(float(p[1]) for p in points), max(float(p[0]) for p in points), max(float(p[1]) for p in points)


def repair_integral(block, spans, picture, engine):
    """原生积分字形可核实时，对误识别公式扩大取框并单独复识，保留真实符号。"""
    if '\\int' in block['text']:
        return block
    box = block_box(block)
    nearby = [span for span in spans if box[0]-8 <= (span['box'][0]+span['box'][2])/2 <= box[2]+8
        and box[1]-4 <= (span['box'][1]+span['box'][3])/2 <= box[3]+4]
    if not any('∫' in span['text'] or '\uf0f2' in span['text'] for span in nearby):
        return block
    math_spans = [span for span in nearby if not re.search(r'[\u4e00-\u9fff]', span['text'])]
    if not math_spans:
        return block
    from PIL import ImageOps
    rect = (max(0, min(span['box'][0] for span in math_spans)-2),
        max(0, min(span['box'][1] for span in math_spans)-4),
        min(picture.width, max(span['box'][2] for span in math_spans)+2),
        min(picture.height, max(span['box'][3] for span in math_spans)+4))
    crop = ImageOps.expand(picture.crop(rect), border=8, fill='white')
    try:
        result = engine.latex_ocr.recognize(crop)
    finally:
        crop.close()
    if isinstance(result, dict) and '\\int' in result.get('text', ''):
        return {**block, 'text': result['text']}
    return block


def restore_native_chinese(block, spans):
    """原生中文字形可读且与OCR同框同长度时，复用原文校正单字误识。"""
    content = re.sub(r'^[\d\s.．、]+', '', block['text']).strip()
    if block.get('type') != 'text' or not re.fullmatch(r'[\u4e00-\u9fff，。、：；？！]+', content):
        return block
    box = block_box(block)
    candidates = [span for span in spans if re.fullmatch(r'[\u4e00-\u9fff，。、：；？！]+', span['text'].strip())
        and box[0]-8 <= (span['box'][0]+span['box'][2])/2 <= box[2]+8
        and box[1]-8 <= (span['box'][1]+span['box'][3])/2 <= box[3]+8]
    text = ''.join(span['text'].strip() for span in sorted(candidates, key=lambda item: item['box'][0]))
    return {**block, 'text': text} if len(text) == len(content) else block


def ordered_page_text(blocks, anchors, spans, picture, engine):
    """题号作为几何锚点，先输出编号再合并本题文字/公式，防止跨题串接。"""
    from .study_sources import SECTION
    blocks = [dict(block) for block in blocks if not re.match(r'^(?:第\s*\d+\s*页.*共\s*\d+\s*页|试卷编号)', block['text'].strip())]
    headers = [dict(kind='section', text=block['text'], box=block_box(block)) for block in blocks
        if SECTION.match(block['text'].strip())]
    events = sorted([*anchors, *headers], key=lambda item: item['box'][1])
    if headers:
        # 跨页续题可能出现在本页第一个大题标题之前，题号锚点也必须保留。
        start = min(event['box'][1] for event in events)
        blocks = [block for block in blocks if block_box(block)[3] >= start]
    groups = [[] for _ in events]
    prefix = []
    for block in blocks:
        if SECTION.match(block['text'].strip()):
            continue
        if block.get('type') in ('embedding', 'isolated'):
            block = repair_integral(block, spans, picture, engine)
        else:
            block = restore_native_chinese(block, spans)
        bottom = block_box(block)[3]
        index = next((i for i in range(len(events)-1, -1, -1) if events[i]['box'][1] <= bottom), -1)
        if index < 0:
            prefix.append(block)
        else:
            event = events[index]
            if event['kind'] == 'question' and block.get('type') == 'text' and block_box(block)[0] < event['box'][0]+45:
                block['text'] = re.sub(r'^\s*' + re.escape(event['number']) + r'(?:[.．、]|(?=[\u4e00-\u9fff]))\s*', '', block['text'])
                block['text'] = re.sub(r'^[.．、]\s*(?=[\u4e00-\u9fff])', '', block['text'])
            groups[index].append(block)

    def merge(items):
        lines = {}
        for block in sorted(items, key=lambda item: (item['line_number'], block_box(item)[0])):
            text = block['text'].strip()
            if block.get('type') in ('embedding', 'isolated'):
                text = '$' + text + '$'
            lines.setdefault(block['line_number'], []).append(text)
        return '\n'.join(' '.join(line).strip() for line in lines.values()).strip()

    output = [merge(prefix)]
    for event, group in zip(events, groups):
        if event['kind'] == 'section':
            output.append(event['text'] + '\n' + merge(group))
        else:
            output.append(event['number'] + '. ' + merge(group))
    return '\n'.join(text for text in output if text.strip())


def cached_pages(material):
    try:
        cache = json.loads(material.pdf_ocr_json or '{}')
    except (ValueError, TypeError):
        return {}
    if not isinstance(cache, dict) or cache.get('engine') != ENGINE_VERSION:
        return {}
    return cache.get('pages', {}) if isinstance(cache.get('pages'), dict) else {}


def recognized_unit(material, unit):
    if material.file_type != 'pdf':
        return {**unit, 'input_hash': None}
    pages = cached_pages(material)
    selected = unit['pages']
    if not selected or any(not isinstance(pages.get(str(number)), str) for number in selected):
        raise HTTPException(409, '原题公式尚未完成本机识别，请重新打开来源后重试')
    text, locations, offset = '', [], 0
    for number in selected:
        body = pages[str(number)]
        locations.append(dict(start=offset, end=offset+len(body), kind='page', number=number, label=f'第 {number} 页'))
        text += body + '\n'
        offset = len(text)
    virtual = SimpleNamespace(id=material.id, created_at=material.created_at, title=material.title,
        source_type=material.source_type, file_type='pdf', parse_status='done', exam_id=material.exam_id,
        text_content=text, text_locations=json.dumps(locations, ensure_ascii=False))
    candidates = material_units(virtual)
    section = re.search(r'第[一二三四五六七八九十]+大题', unit['label'])
    matches = [item for item in candidates if unit['question_number'] and item['question_number'] == unit['question_number']
        and (section is None or section[0] in item['label'])]
    # 题号唯一时只交给模型这一题；不确定时保留按阅读顺序识别的原页及真实编号。
    if len(matches) == 1:
        chosen = matches[0]
        text = chosen['text']
        label, selected = chosen['label'], chosen['pages']
        location, subquestions = chosen['location'], chosen['subquestions']
    else:
        label = unit['label']
        location, subquestions = unit['location'], unit['subquestions']
    digest = content_hash(ENGINE_VERSION + '\n' + text)
    return {**unit, 'text': text.strip(), 'label': label, 'pages': selected, 'location': location, 'subquestions': subquestions,
        'question_identified': len(matches) == 1,
        'input_hash': digest, 'recognition': '已在本机按原页重新识别中文和公式，题号及公式仍可对照图片核对。'}


def prepare_source(db, user, material, unit):
    if material.file_type != 'pdf':
        return recognized_unit(material, unit)
    from ..models.models import Material
    from .task_conflicts import lock_schedule
    uid, key = user.id, user.auth_key
    identity = material.id, material.created_at, content_hash(material.text_content), material.file_path
    pages = unit['pages']
    if not pages:
        raise HTTPException(422, '该来源没有可靠页码，请从原页重新选择题目')
    path = _upload_path(material.file_path, UPLOAD_DIR)
    if not path.is_file():
        raise HTTPException(404, '原文件不存在，请重新上传')
    # 不在OCR下载/推理期间持有数据库事务或写锁。
    db.rollback()
    with _recognition_lock:
        current = db.get(Material, identity[0], populate_existing=True)
        if (current is None or current.user_id != uid or current.created_at != identity[1]
                or current.file_path != identity[3] or content_hash(current.text_content) != identity[2]):
            raise HTTPException(409, '资料已删除或替换，请刷新来源列表')
        cache = cached_pages(current)
        missing = [number for number in pages if str(number) not in cache]
        db.rollback()
        if missing:
            try:
                additions = recognize_pdf_pages(path, missing)
            except Exception as exc:
                raise HTTPException(422, '本机公式识别未完成，请运行 backend/tools/prepare_ocr.py 检查模型与下载连接后重试') from exc
            lock_schedule(db, uid, auth_key=key)
            current = db.get(Material, identity[0], populate_existing=True)
            if (current is None or current.created_at != identity[1] or current.user_id != uid
                    or current.file_path != identity[3] or content_hash(current.text_content) != identity[2]):
                db.rollback()
                raise HTTPException(409, '识别期间资料发生变化，请重新选择')
            cache = {**cached_pages(current), **additions}
            current.pdf_ocr_json = json.dumps({'engine': ENGINE_VERSION, 'pages': cache}, ensure_ascii=False)
            db.commit()
        material = db.get(Material, identity[0], populate_existing=True)
        return recognized_unit(material, unit)
