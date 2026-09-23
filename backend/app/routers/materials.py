"""复习资料接口：上传（含解析）/ 列表筛选 / 详情预览 / 删除"""
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ..config import UPLOAD_DIR, settings
from ..database import get_db
from ..models.models import Exam, Material, User
from ..schemas.schemas import MaterialDetailOut, MaterialOut
from ..services.file_parser import parse_file
from ..utils.security import get_current_user

router = APIRouter()

ALLOWED_TYPES = {"txt", "pdf", "docx"}

SOURCE_TYPES = {"历年题", "老师重点", "课堂笔记", "作业", "练习题", "其他"}


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
    if source_type not in SOURCE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"来源类型必须是：{'/'.join(sorted(SOURCE_TYPES))}",
        )
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


@router.get("", response_model=list[MaterialOut], summary="资料列表（可按科目/关键词/来源类型筛选）")
def list_materials(
    exam_id: int | None = None,
    keyword: str | None = None,
    source_type: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Material).filter(Material.user_id == user.id)
    if exam_id is not None:
        query = query.filter(Material.exam_id == exam_id)
    if source_type:
        query = query.filter(Material.source_type == source_type)
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(
            (Material.title.like(like))
            | (Material.description.like(like))
            | (Material.tags.like(like))
        )
    return query.order_by(Material.id.desc()).all()


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
    db.delete(material)
    db.commit()
    return {"ok": True}
