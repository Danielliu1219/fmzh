"""上传文件统一校验（公共功能 · 用例 9.5 / FMZH-SRS-0.5.0）

所有上传入口都走这里，保证校验口径一致：
    1) 扩展名是否在允许列表内
    2) 文件大小是否超过上限（单文件 20MB）
    3) 后缀与内容头安全扫描 —— 拒绝「改了扩展名的伪装文件」

校验不通过抛 UploadRejected，由路由层转成 400 并把原因提示给用户。
允许列表由调用方传入，便于不同入口各自规定格式范围（复习资料 / 头像等）。
"""
from pathlib import Path
from io import BytesIO
from zipfile import ZipFile, BadZipFile

MAX_UPLOAD_SIZE_MB = 20

# 内容头（magic bytes）特征。Office Open XML（docx/pptx/xlsx）本质都是 ZIP 容器
CONTENT_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "pdf": (b"%PDF-",),
    "docx": (b"PK\x03\x04",),
    "pptx": (b"PK\x03\x04",),
    "ppt": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
    "xlsx": (b"PK\x03\x04",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
}

# 纯文本类没有固定魔数，改用「开头不含 NUL 等二进制字节」来间接判断
TEXT_LIKE = {"txt", "md", "csv"}

# UTF-16 文本按 BOM 识别：正常编码的 UTF-16 也会出现 NUL 字节，需先放行再做 NUL 扫描
UTF16_BOMS = (b"\xff\xfe", b"\xfe\xff")


class UploadRejected(Exception):
    """上传校验未通过；异常消息可直接回给前端"""


def check_extension(filename: str, allowed: set[str]) -> str:
    """扩展名白名单校验，返回规范化后的小写扩展名"""
    ext = Path(filename or "").suffix.lower().lstrip(".")
    if not ext:
        raise UploadRejected("文件没有扩展名，无法识别格式")
    if ext not in allowed:
        raise UploadRejected(f"仅支持 {', '.join(sorted(allowed))} 格式，收到：.{ext}")
    return ext


def check_size(content: bytes, max_mb: int = MAX_UPLOAD_SIZE_MB) -> None:
    """大小上限校验（并拒收空文件）"""
    if not content:
        raise UploadRejected("文件为空")
    limit = max_mb * 1024 * 1024
    if len(content) > limit:
        # 注意：路由层为防超限，只读到「上限 + 1 字节」，所以这里不报具体大小（会偏小）
        raise UploadRejected(f"文件超过 {max_mb}MB 上限，请压缩后重新上传")


def check_content_head(content: bytes, ext: str) -> None:
    """后缀与内容头安全扫描：内容与扩展名不符（改过名的伪装文件）则拒绝"""
    signatures = CONTENT_SIGNATURES.get(ext)
    if signatures:
        head = content[:16]
        if not any(head.startswith(sig) for sig in signatures):
            raise UploadRejected(f"文件内容与扩展名 .{ext} 不符（可能被改过名），已拒绝上传")
        if ext in ('docx','pptx'):
            _check_office(content, ext)
        elif ext == 'ppt':
            import olefile
            try:
                with olefile.OleFileIO(BytesIO(content)) as doc:
                    if not doc.exists('PowerPoint Document'):
                        raise ValueError('not PowerPoint')
            except Exception as exc:
                raise UploadRejected('文件不是有效的PPT文档') from exc
        elif ext in ('png','jpg','jpeg'):
            from PIL import Image
            try:
                with Image.open(BytesIO(content)) as pic:
                    if pic.width*pic.height > 25_000_000 or pic.format != ('PNG' if ext == 'png' else 'JPEG'):
                        raise ValueError('image size or format')
                    pic.verify()
                # JPEG.verify不解码像素；再次解码才能拒绝完整头部下的损坏压缩数据。
                with Image.open(BytesIO(content)) as pic:
                    pic.load()
            except Exception as exc:
                raise UploadRejected('图片损坏、格式不符或像素过大，请使用2500万像素以内的PNG/JPEG') from exc
        return
    if ext in TEXT_LIKE:
        head = content[:4096]
        # 带 BOM 的 UTF-16 文本不是伪装文件：ASCII 字符的高字节为 0，属正常编码
        if head.startswith(UTF16_BOMS):
            return
        if b"\x00" in head:
            raise UploadRejected("该文件含二进制内容，不像纯文本，已拒绝上传")


def _check_office(content, ext):
    import zlib
    from pathlib import PurePosixPath
    from xml.etree import ElementTree as ET
    required = 'word/document.xml' if ext == 'docx' else 'ppt/presentation.xml'
    root = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}document' if ext == 'docx' else '{http://schemas.openxmlformats.org/presentationml/2006/main}presentation'
    try:
        with ZipFile(BytesIO(content)) as package:
            infos = package.infolist()
            if len(infos)>4000 or len({i.filename for i in infos}) != len(infos) or sum(i.file_size for i in infos)>100*1024*1024:
                raise ValueError('archive limits')
            if any(i.flag_bits & 1 or i.file_size>40*1024*1024 or PurePosixPath(i.filename).is_absolute() or '..' in PurePosixPath(i.filename).parts or '\\' in i.filename or ':' in i.filename for i in infos):
                raise ValueError('archive entry')
            if required not in package.namelist() or '[Content_Types].xml' not in package.namelist():
                raise ValueError('missing office parts')
            xml = package.read(required)
            if b'<!DOCTYPE' in xml.upper() or ET.fromstring(xml).tag != root or package.testzip() is not None:
                raise ValueError('invalid office XML')
    except (BadZipFile, ValueError, KeyError, ET.ParseError, RuntimeError, NotImplementedError, OSError, EOFError, zlib.error) as exc:
        raise UploadRejected(f'文件不是有效的.{ext}文档，或压缩内容超出安全范围') from exc


def validate_upload(
    filename: str,
    content: bytes,
    allowed: set[str],
    max_mb: int = MAX_UPLOAD_SIZE_MB,
) -> str:
    """统一校验入口：扩展名 → 大小 → 内容头，返回规范化扩展名

    其他上传入口（如头像）可以直接调用这个一次搞定；需要「先按扩展名快速拒绝、
    避免白读大文件」时，也可以先单独调 check_extension，读完再调后两个。
    """
    ext = check_extension(filename, allowed)
    check_size(content, max_mb)
    check_content_head(content, ext)
    return ext
