"""文件解析：把上传文件提取成纯文本

MVP 支持：TXT / PDF / DOCX
扩展预留：PPT（python-pptx）、图片 OCR
"""
from pathlib import Path

# 解析出的文本上限（字符），避免超大文件占满内存
MAX_TEXT_LENGTH = 200_000


def parse_file(path: Path, file_type: str) -> str:
    """按文件类型解析，返回纯文本；失败抛出 ValueError"""
    text = ""
    if file_type == "txt":
        text = _parse_txt(path)
    elif file_type == "pdf":
        text = _parse_pdf(path)
    elif file_type == "docx":
        text = _parse_docx(path)
    else:
        raise ValueError(f"暂不支持的文件类型：{file_type}")
    text = (text or "").strip()
    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH]
    return text


def _parse_txt(path: Path) -> str:
    # 常见编码依次尝试：UTF-8 / GBK / UTF-16
    for encoding in ("utf-8", "gbk", "utf-16"):
        try:
            return path.read_text(encoding=encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
    # 全部失败时忽略错误字符兜底
    return path.read_text(encoding="utf-8", errors="ignore")


def _parse_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _parse_docx(path: Path) -> str:
    from docx import Document

    doc = Document(str(path))
    parts = [p.text for p in doc.paragraphs]
    # 顺带提取表格中的文字
    for table in doc.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text for cell in row.cells))
    return "\n".join(parts)
