"""文件解析：把上传文件提取成纯文本

支持 TXT / PDF / DOCX / PPT / PPTX / PNG / JPEG；OCR仅在本机运行。
"""
from pathlib import Path
from threading import Lock
_ocr_lock=Lock()

# 解析出的文本上限（字符），避免超大文件占满内存
MAX_TEXT_LENGTH = 200_000


def parse_file(path: Path, file_type: str) -> str:
    """按文件类型解析，返回纯文本；失败抛出 ValueError"""
    return parse_document(path, file_type)[0]


def parse_document(path: Path, file_type: str) -> tuple[str, list[dict]]:
    """保留真实页码/段落/行号；偏移始终相对最终保存的解析文本。"""
    if file_type == "txt":
        text = _parse_txt(path)
        left = len(text) - len(text.lstrip())
        parts, offset = [], left
        first_line = text[:left].count('\n') + 1
        for line_number, line in enumerate(text[left:left+MAX_TEXT_LENGTH].splitlines(keepends=True), first_line):
            end = offset + len(line.rstrip('\r\n'))
            parts.append(dict(start=offset, end=end, kind='line', number=line_number, label=f'第 {line_number} 行'))
            offset += len(line)
    elif file_type == "pdf":
        from pypdf import PdfReader
        import re
        pages = []
        total = 0
        for index, page in enumerate(PdfReader(str(path)).pages, 1):
            body = (page.extract_text(extraction_mode='layout') or '') if '/Contents' in page else ''
            # 数学字体的私用区字符、二维公式及扫描页交给混合OCR保留公式结构。
            if not body.strip() or re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x80-\x9f\ue000-\uf8ff∫∑√=<>]|\b(?:lim|sin|cos)\b', body):
                from .pdf_recognition import recognize_pdf_pages
                body = recognize_pdf_pages(path, [index])[str(index)]
            pages.append(body)
            total += len(body)
            if total >= MAX_TEXT_LENGTH:
                break
        text, parts = _join_parts([(body, 'page', index, f'第 {index} 页') for index, body in enumerate(pages, 1)])
    elif file_type == "docx":
        from docx import Document
        document = Document(str(path))
        chunks = [(p.text, 'paragraph', index, f'第 {index} 段') for index, p in enumerate(document.paragraphs, 1)]
        for table_number, table in enumerate(document.tables, 1):
            for row_number, row in enumerate(table.rows, 1):
                chunks.append((' | '.join(cell.text for cell in row.cells), 'table_row', row_number, f'表 {table_number} · 第 {row_number} 行'))
        text, parts = _join_parts(chunks)
    elif file_type == 'pptx':
        from pptx import Presentation
        slides = []
        for index, slide in enumerate(Presentation(str(path)).slides,1):
            lines = []
            for shape in slide.shapes:
                if shape.has_text_frame: lines.append(shape.text)
                if shape.has_table:
                    lines.extend(' | '.join(cell.text for cell in row.cells) for row in shape.table.rows)
            slides.append(('\n'.join(lines),'slide',index,f'第 {index} 张幻灯片'))
        text, parts = _join_parts(slides)
    elif file_type == 'ppt':
        import olefile
        import struct
        with olefile.OleFileIO(str(path)) as document:
            raw = document.openstream('PowerPoint Document').read(40*1024*1024+1)
        if len(raw)>40*1024*1024: raise ValueError('PPT内容过大')
        lines=[]
        text_length = records = 0
        def atoms(start,end,depth=0):
            nonlocal text_length, records
            if depth>32: raise ValueError('PPT结构嵌套过深')
            cursor=start
            while cursor+8<=end and text_length<MAX_TEXT_LENGTH:
                records += 1
                if records > 200000: raise ValueError('PPT记录过多')
                info,kind,size=struct.unpack_from('<HHI',raw,cursor)
                body=cursor+8;stop=body+size
                if stop>end: raise ValueError('PPT记录损坏')
                if info & 15 == 15: atoms(body,stop,depth+1)
                elif kind in (4000,4008):
                    line=raw[body:stop].decode('utf-16-le' if kind==4000 else 'cp1252',errors='replace')[:MAX_TEXT_LENGTH-text_length]
                    lines.append(line)
                    text_length += len(line)
                cursor=stop
        atoms(0,len(raw))
        text, parts = _join_parts([(line,'paragraph',i,f'PPT文本段 {i}') for i,line in enumerate(lines,1)])
    elif file_type in ('png','jpg','jpeg'):
        lines = _parse_image(path)
        text, parts = _join_parts([(line,'image_line',i,f'图片识别第 {i} 行') for i,line in enumerate(lines,1)])
    else:
        raise ValueError(f"暂不支持的文件类型：{file_type}")
    left = len(text) - len(text.lstrip())
    retained = text.strip()[:MAX_TEXT_LENGTH]
    locations = []
    for part in parts:
        start, end = max(0, part['start'] - left), min(len(retained), part['end'] - left)
        if start < end and retained[start:end].strip():
            locations.append({**part, 'start': start, 'end': end})
    return retained, locations


def _parse_image(path):
    from PIL import Image
    import numpy as np
    # 首次初始化会下载免费的OCR权重；用户图片仅在本机推理，不发送第三方。
    with Image.open(path) as pic:
        pic = pic.convert('RGB')
        pic.thumbnail((2400,2400))
        with _ocr_lock:
            output = _ocr_engine()(np.asarray(pic))
    return list(output.txts) if output.txts is not None else []


from functools import lru_cache
@lru_cache(maxsize=1)
def _ocr_engine():
    from rapidocr import RapidOCR
    return RapidOCR(params={'EngineConfig.onnxruntime.intra_op_num_threads':2})


def warm_image_ocr():
    """启动时预热图片OCR；模型随包提供，通常不到1秒。"""
    _ocr_engine()


def _join_parts(chunks):
    texts, locations, offset = [], [], 0
    for text, kind, number, label in chunks:
        texts.append(text)
        locations.append(dict(start=offset, end=offset + len(text), kind=kind, number=number, label=label))
        offset += len(text) + 1
    return '\n'.join(texts), locations


def _parse_txt(path: Path) -> str:
    # 常见编码依次尝试：UTF-8 / GBK / UTF-16
    for encoding in ("utf-8", "gbk", "utf-16"):
        try:
            return path.read_text(encoding=encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
    # 全部失败时忽略错误字符兜底
    return path.read_text(encoding="utf-8", errors="ignore")
