"""有权限校验、版本校验的复习来源库与原文件查看。"""
import io
import json
from pathlib import Path
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import UPLOAD_DIR, BASE_DIR
from ..database import get_db
from ..models.models import Analysis, Exam, Material, User
from ..schemas.schemas import AnalysisResult
from ..services.study_sources import library, material_units, unit_detail
from ..services.source_evidence import content_hash
from ..services.mistakes import save_question
from ..services.task_conflicts import lock_schedule
from ..utils.security import get_current_user

router = APIRouter()
_pdf_lock = Lock()  # PDFium不是线程安全的；仅渲染当前用户选中的一页。
PRIVATE = {'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'}


def own_material(db, user, material_id):
    row = db.query(Material).filter(Material.id == material_id, Material.user_id == user.id).first()
    if row is None: raise HTTPException(404, '资料不存在')
    return row


def checked_unit(material, unit_id):
    unit = next((u for u in material_units(material) if u['id'] == unit_id), None)
    if unit is None: raise HTTPException(409, '资料已变化或原定位失效，请刷新来源列表')
    return unit


@router.get('')
def sources(exam_id: int, analysis_id: int | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not db.query(Exam.id).filter(Exam.id == exam_id, Exam.user_id == user.id).first():
        raise HTTPException(404, '考试不存在')
    result = None
    query = db.query(Analysis).filter(Analysis.user_id == user.id, Analysis.exam_id == exam_id)
    analysis = query.filter(Analysis.id == analysis_id).first() if analysis_id else query.order_by(Analysis.id.desc()).first()
    if analysis_id and not analysis: raise HTTPException(404, '分析不存在或不属于当前科目')
    if analysis:
        try: result = AnalysisResult.model_validate_json(analysis.result_json)
        except ValueError: raise HTTPException(409, '分析记录无法读取，请在资料库中查看原文')
    rows = db.query(Material).filter(Material.user_id == user.id, Material.exam_id == exam_id).order_by(Material.id).all()
    items = library(rows, result)
    return dict(exam_id=exam_id, analysis_id=analysis.id if analysis else None, items=items,
        note='题号为本地识别；引文/关键词匹配仅供定位，请核对原页。未匹配内容仍可在全部来源中选择。')


@router.get('/{material_id}/unit')
def detail(material_id: int, unit_id: str = Query(max_length=160), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return unit_detail(checked_unit(own_material(db, user, material_id), unit_id))


class DifficultIn(BaseModel):
    unit_id: str = Field(min_length=1, max_length=160)
    knowledge_point: str = Field('', max_length=128)


@router.post('/{material_id}/difficult')
def mark_difficult(material_id: int, payload: DifficultIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    lock_schedule(db, user.id, auth_key=user.auth_key)
    unit = unit_detail(checked_unit(own_material(db, user, material_id), payload.unit_id))
    body = dict(question=unit['question_text'], answer=unit['original_answer'], analysis='用户标记不会，待复习。',
                knowledge_point=payload.knowledge_point, source_reference=dict(material_id=material_id,id=unit['id'],exam_id=unit['exam_id']),
                source_label=unit['label'], exam_id=unit['exam_id'])
    item, added = save_question(db, user.id, f"{unit['material_title']} · {unit['label']}", json.dumps(body,ensure_ascii=False),
                               'manual', identity='study-source:'+unit['id'])
    db.commit()
    request.state.audit_target = item.id
    return dict(id=item.id, added=added)


@router.get('/{material_id}/original')
def original(material_id: int, page: int | None = Query(None, ge=1), unit_id: str | None = Query(None, max_length=160),
             revision: str | None = Query(None, pattern='^[a-f0-9]{64}$'), download: bool = False,
             user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    material = own_material(db, user, material_id)
    if revision and revision != content_hash(material.text_content): raise HTTPException(409, '资料已变化，请刷新来源')
    if unit_id:
        unit = checked_unit(material, unit_id)
        if page is not None and page not in unit['pages']: raise HTTPException(422, '该页不在当前来源范围内')
    path = Path(material.file_path)
    if not path.is_absolute(): path = BASE_DIR / path
    path = path.resolve()
    if not path.is_relative_to(UPLOAD_DIR.resolve()) or not path.is_file():
        raise HTTPException(404, '原文件不存在，请重新上传资料')
    if material.file_type == 'pdf' and page is not None and not download:
        try:
            import pypdfium2 as pdfium
            with _pdf_lock, pdfium.PdfDocument(str(path)) as pdf:
                if page > len(pdf): raise HTTPException(404, '原文件没有该页')
                pdf_page = pdf[page-1]
                try:
                    width, height = pdf_page.get_size()
                    if width <= 0 or height <= 0: raise ValueError('invalid size')
                    scale = min(2, 1800/max(width, height))
                    bitmap = pdf_page.render(scale=scale)
                    try:
                        stream = io.BytesIO()
                        bitmap.to_pil().save(stream, format='PNG')
                    finally: bitmap.close()
                finally: pdf_page.close()
            return Response(stream.getvalue(), media_type='image/png', headers=PRIVATE)
        except HTTPException: raise
        except Exception: raise HTTPException(422, '原页无法渲染，请下载原文件查看')
    media = {'pdf':'application/pdf', 'png':'image/png', 'jpg':'image/jpeg', 'jpeg':'image/jpeg'}.get(material.file_type, 'application/octet-stream')
    return FileResponse(path, media_type=media, filename=f'{material.title}.{material.file_type}',
                        content_disposition_type='attachment' if download or media == 'application/octet-stream' else 'inline', headers=PRIVATE)
