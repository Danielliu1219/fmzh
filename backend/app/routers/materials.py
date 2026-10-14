"""复习资料接口：上传（含解析）/ 列表筛选 / 详情预览 / 编辑移动分类 / 删除"""
import uuid
from datetime import date, datetime, time
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ..config import UPLOAD_DIR, settings
from ..database import get_db
from ..models.models import Collection, Exam, Material, User
from ..schemas.schemas import (
    MaterialDetailOut,
    MaterialMergeIn,
    MaterialMergeOut,
    MaterialOut,
    MaterialUpdate,
)
from ..services.file_parser import parse_file
from ..utils.security import get_current_user

router = APIRouter()

ALLOWED_TYPES = {"txt", "pdf", "docx"}

# 资料七类来源（需求分析 3.3.3.2 / FMZH-USR-0029），外加「其他」作为兜底默认值
SOURCE_TYPES = ("历年题", "老师重点", "平时作业", "课堂笔记", "教材章节", "实验报告", "练习题", "其他")


SORT_OPTIONS = {
    "date_desc": (Material.created_at.desc(), Material.id.desc()),
    "date_asc": (Material.created_at.asc(), Material.id.asc()),
    "title": (Material.title.asc(), Material.id.asc()),
    "source_type": (Material.source_type.asc(), Material.created_at.desc()),
    "exam": (Material.exam_id.asc(), Material.created_at.desc()),
}


def _match_snippet(text: str, keyword: str, width: int = 80) -> str:
    """全文搜索命中片段：截关键词前后各约 width/2 字，供前端展示命中位置"""
    idx = (text or "").find(keyword)
    if idx < 0:
        return ""
    start = max(0, idx - width // 2)
    end = min(len(text), idx + len(keyword) + width // 2)
    body = text[start:end].replace("\n", " ").strip()
    return f"{'…' if start > 0 else ''}{body}{'…' if end < len(text) else ''}"


def _check_source_type(source_type: str) -> None:
    """上传与编辑共用的来源类型白名单校验（用例 3.2）"""
    if source_type not in SOURCE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"来源类型必须是：{'/'.join(SOURCE_TYPES)}",
        )


def _get_own_material(db: Session, user: User, material_id: int) -> Material:
    material = (
        db.query(Material)
        .filter(Material.id == material_id, Material.user_id == user.id)
        .first()
    )
    if material is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资料不存在")
    return material


@router.post("", response_model=MaterialOut, summary="上传复习资料（TXT/PDF/DOCX，上传后自动解析）")
async def upload_material(
    file: UploadFile = File(...),
    title: str = Form(...),
    exam_id: int | None = Form(None),
    source_type: str = Form("其他"),
    description: str = Form(""),
    tags: str = Form(""),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 校验扩展名
    ext = Path(file.filename or "").suffix.lower().lstrip(".")
    if ext not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"仅支持 {', '.join(sorted(ALLOWED_TYPES))} 格式（MVP 阶段），收到：{ext or '未知'}",
        )
    _check_source_type(source_type)
    if exam_id is not None:
        exam = db.query(Exam).filter(Exam.id == exam_id, Exam.user_id == user.id).first()
        if exam is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="考试不存在")

    # 读取并校验大小
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"文件超过 {settings.MAX_UPLOAD_SIZE_MB}MB 上限",
        )
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件为空")

    # 保存到 uploads/{user_id}/{随机名}.{ext}
    user_dir = UPLOAD_DIR / str(user.id)
    user_dir.mkdir(parents=True, exist_ok=True)
    stored_path = user_dir / f"{uuid.uuid4().hex}.{ext}"
    stored_path.write_bytes(content)

    # 解析正文
    text_content = ""
    parse_status = "done"
    try:
        text_content = parse_file(stored_path, ext)
    except Exception:
        # 解析失败不阻断上传：资料仍保存，标记为 failed，前端展示提示
        parse_status = "failed"

    material = Material(
        user_id=user.id,
        exam_id=exam_id,
        title=title.strip() or (file.filename or "未命名资料"),
        source_type=source_type,
        file_path=str(stored_path),  # 存绝对路径，删除文件时不依赖启动目录
        file_type=ext,
        text_content=text_content,
        parse_status=parse_status,
        description=description,
        tags=tags,
    )
    db.add(material)
    db.commit()
    db.refresh(material)
    return material


@router.get("", response_model=list[MaterialOut], summary="资料列表（全文搜索 + 科目/来源/标签/日期筛选 + 排序）")
def list_materials(
    exam_id: int | None = None,
    keyword: str | None = None,
    source_type: str | None = None,
    tag: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    sort: str = "date_desc",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Material).filter(Material.user_id == user.id)
    if exam_id is not None:
        query = query.filter(Material.exam_id == exam_id)
    if source_type:
        query = query.filter(Material.source_type == source_type)
    if tag:
        query = query.filter(Material.tags.like(f"%{tag}%"))
    if date_from is not None:
        query = query.filter(Material.created_at >= datetime.combine(date_from, time.min))
    if date_to is not None:
        query = query.filter(Material.created_at <= datetime.combine(date_to, time.max))

    keyword = (keyword or "").strip()
    if keyword:
        like = f"%{keyword}%"
        # 全文搜索：命中解析出的正文 text_content（用例 3.4），而不只是标题/说明/标签
        query = query.filter(
            (Material.title.like(like))
            | (Material.description.like(like))
            | (Material.tags.like(like))
            | (Material.text_content.like(like))
        )

    items = query.order_by(*SORT_OPTIONS.get(sort, SORT_OPTIONS["date_desc"])).all()
    if keyword:
        for item in items:
            item.snippet = _match_snippet(item.text_content or "", keyword)
    return items


@router.get("/{material_id}", response_model=MaterialDetailOut, summary="资料详情（含解析文本预览）")
def get_material(
    material_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    material = _get_own_material(db, user, material_id)
    out = MaterialDetailOut.model_validate(material)
    out.text_preview = material.text_content[:1000]
    return out


@router.put("/{material_id}", response_model=MaterialOut, summary="编辑资料 / 移动分类（用例 3.3）")
def update_material(
    material_id: int,
    payload: MaterialUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    material = _get_own_material(db, user, material_id)
    data = payload.model_dump(exclude_unset=True)  # 只处理请求里出现的字段

    if "title" in data:
        title = (data["title"] or "").strip()
        if not title:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="标题不能为空")
        data["title"] = title
    if "source_type" in data:
        _check_source_type(data["source_type"])
    if data.get("exam_id") is not None:
        exam = db.query(Exam).filter(Exam.id == data["exam_id"], Exam.user_id == user.id).first()
        if exam is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="考试不存在")

    for field, value in data.items():
        setattr(material, field, value)
    db.commit()
    db.refresh(material)
    return material


MERGE_MAX_CHARS_PER_MATERIAL = 20000  # 单份资料导出时的正文上限，防止合成出超大文件


@router.post("/merge", response_model=MaterialMergeOut, summary="合并多份资料为一份复习笔记（用例 3.6）")
def merge_materials(
    payload: MaterialMergeIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """把勾选的多份资料按顺序合并成一份 Markdown 复习笔记（导出格式由前端决定）"""
    ids = list(dict.fromkeys(payload.material_ids))  # 去重且保持勾选顺序
    items = (
        db.query(Material)
        .filter(Material.user_id == user.id, Material.id.in_(ids))
        .all()
    )
    by_id = {m.id: m for m in items}
    missing = [i for i in ids if i not in by_id]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"资料不存在或不属于当前用户：{missing}",
        )

    # 所属科目名：一次查出来，避免在循环里逐条查询
    exam_ids = {m.exam_id for m in items if m.exam_id is not None}
    subjects = {}
    if exam_ids:
        exams = db.query(Exam).filter(Exam.user_id == user.id, Exam.id.in_(exam_ids)).all()
        subjects = {e.id: e.subject for e in exams}

    title = payload.title.strip() or "复习笔记"
    lines = [
        f"# {title}",
        "",
        f"> 由「期末周别慌」合并生成 · 共 {len(ids)} 份资料 · {datetime.now():%Y-%m-%d %H:%M}",
        "",
    ]
    warnings: list[str] = []
    total_chars = 0
    for index, material_id in enumerate(ids, start=1):
        material = by_id[material_id]
        lines += [f"## {index}. {material.title}", ""]

        meta = [f"来源类型：{material.source_type}"]
        if material.exam_id in subjects:
            meta.append(f"所属科目：{subjects[material.exam_id]}")
        if material.tags:
            meta.append(f"标签：{material.tags}")
        if material.description:
            meta.append(f"说明：{material.description}")
        lines += ["- " + " · ".join(meta), ""]

        body = (material.text_content or "").strip()
        if not body:
            lines += ["> 该资料没有可导出的正文（解析失败或为扫描件）。", ""]
            warnings.append(f"《{material.title}》没有解析正文")
        else:
            if len(body) > MERGE_MAX_CHARS_PER_MATERIAL:
                body = body[:MERGE_MAX_CHARS_PER_MATERIAL]
                warnings.append(
                    f"《{material.title}》正文过长，已截取前 {MERGE_MAX_CHARS_PER_MATERIAL} 字"
                )
            lines += [body, ""]
            total_chars += len(body)
        lines += ["---", ""]

    while lines and lines[-1] in ("", "---"):
        lines.pop()

    return MaterialMergeOut(
        title=title,
        markdown="\n".join(lines) + "\n",
        material_count=len(ids),
        total_chars=total_chars,
        warnings=warnings,
    )


@router.delete("/{material_id}", summary="删除资料（同时删除磁盘文件）")
def delete_material(
    material_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    material = _get_own_material(db, user, material_id)
    # 删除磁盘文件（失败不影响数据库删除）
    try:
        Path(material.file_path).unlink(missing_ok=True)
    except Exception:
        pass
    # 连带清掉指向这份资料的收藏，避免收藏本里留下空壳（用例 3.5）
    db.query(Collection).filter(
        Collection.user_id == user.id, Collection.material_id == material_id
    ).delete(synchronize_session=False)
    db.delete(material)
    db.commit()
    return {"ok": True}
