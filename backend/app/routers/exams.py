"""考试接口：增删改查（均限定为当前登录用户自己的数据）

考试与日程扩展用例：
- 2.4 筛选查看考试列表（按科目 / 日期区间）
- 2.7 按考试日期倒推生成备考时间表（调用 services/schedule_service）
- 2.12 ICS 导入：解析 ICS 为学习任务，合并前做冲突检测
- 2.13 ICS 导出：考试与任务导出为 ICS 日历文件
"""
from ..services.pressure import beijing_day
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..config import settings
from ..models.models import Exam, Task, User, Course
from ..schemas.schemas import (
    ExamCreate,
    ExamOut,
    ExamUpdate,
    IcsImportResult,
    IcsImportPreview,
    IcsImportConfirm,
    ScheduleGenerateOut,
    ScheduleGenerateRequest,
)
from ..services import schedule_service
from ..services import deletion
from ..services import ics_import
from ..services.calendar_io import export_calendar
from ..services.task_conflicts import lock_schedule
from ..utils.security import get_current_user

router = APIRouter()


def _get_own_exam(db: Session, user: User, exam_id: int) -> Exam:
    exam = db.query(Exam).filter(Exam.id == exam_id, Exam.user_id == user.id).first()
    if exam is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="考试不存在")
    return exam


def catalog_subject(db, subject):
    courses = db.query(Course).filter(Course.name == subject).with_for_update().all()
    active = next((course for course in courses if course.is_active), None)
    if courses and active is None:
        raise HTTPException(409, "该课程已停用，请选择其他启用课程或自建科目")
    return active


@router.get("/course-options", summary="学生可选的启用课程")
def course_options(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return [
        dict(id=c.id, name=c.name, code=c.code, color=c.color)
        for c in db.query(Course)
        .filter(Course.is_active.is_(True))
        .order_by(Course.name, Course.id)
    ]


@router.get("", response_model=list[ExamOut], summary="我的考试列表（按考试时间排序，支持按科目/日期筛选）")
def list_exams(
    subject: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """2.4 筛选查看：subject 模糊匹配，date_from/date_to 限定考试日期区间（参数均可选）"""
    query = db.query(Exam).filter(Exam.user_id == user.id)
    if subject:
        query = query.filter(Exam.subject.contains(subject.strip()))
    if date_from is not None:
        query = query.filter(Exam.exam_date >= date_from)
    if date_to is not None:
        query = query.filter(Exam.exam_date <= date_to)
    return query.order_by(Exam.exam_date, Exam.id).all()


@router.post("", response_model=ExamOut, summary="录入考试")
def create_exam(
    payload: ExamCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    lock_schedule(db, user.id, auth_key=user.auth_key)
    course=catalog_subject(db,payload.subject)
    exam = Exam(user_id=user.id, **payload.model_dump())
    if course and not exam.color: exam.color=course.color
    db.add(exam)
    db.commit()
    db.refresh(exam)
    request.state.audit_target = exam.id
    return exam


@router.put("/{exam_id}", response_model=ExamOut, summary="修改考试")
def update_exam(
    exam_id: int,
    payload: ExamUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    lock_schedule(db, user.id, auth_key=user.auth_key)
    exam = _get_own_exam(db, user, exam_id)
    if payload.subject is not None and payload.subject!=exam.subject:
        course=catalog_subject(db,payload.subject)
        if course and payload.color is None: exam.color=course.color
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is None and field != 'exam_time':
            raise HTTPException(422, '考试字段不能为null；仅考试时刻可清空')
        setattr(exam, field, value)
    db.commit()
    db.refresh(exam)
    return exam


@router.delete("/{exam_id}", summary="删除考试")
def delete_exam(
    exam_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    deletion.delete_exam(db, user.id, exam_id)
    return {"ok": True}


@router.post("/{exam_id}/generate-schedule", response_model=ScheduleGenerateOut, summary="倒推生成备考时间表（2.7）")
def generate_schedule(
    exam_id: int,
    payload: ScheduleGenerateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exam = _get_own_exam(db, user, exam_id)
    try:
        result = schedule_service.generate_schedule(
            db,
            user.id,
            exam,
            daily_minutes=payload.daily_minutes,
            start_date=payload.start_date,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return ScheduleGenerateOut(**result)


@router.post("/import-ics", response_model=IcsImportPreview, summary="ICS 导入预览（不写库）")
async def import_ics(
    file: UploadFile = File(...),
    exam_id: int = Form(...),
    daily_limit_minutes: int | None = Form(None, ge=30, le=960),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exam = _get_own_exam(db, user, exam_id)
    if not (file.filename or "").lower().endswith(".ics"):
        raise HTTPException(400, "请选择 .ics 日历文件")
    limit = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    raw = await file.read(limit + 1)
    if len(raw) > limit:
        raise HTTPException(413, "日历文件超过允许大小")
    if not raw or b"\x00" in raw:
        raise HTTPException(400, "日历文件为空或不是有效文本")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = raw.decode("gb18030")
        except UnicodeDecodeError:
            raise HTTPException(400, "日历文件需要 UTF-8 或 GB18030 编码")
    return ics_import.preview_import(db, user, exam, text, daily_limit_minutes)


@router.post("/import-ics/confirm", response_model=IcsImportResult, summary="确认导入预览中的日历任务")
def confirm_ics(
    payload: IcsImportConfirm,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return ics_import.confirm_import(db, user, payload.preview_token)


@router.get("/export-ics", summary="导出标准日历（含文本转义和 UTF-8 折行）")
def export_ics(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exams = db.query(Exam).filter(Exam.user_id == user.id).order_by(Exam.exam_date, Exam.id).all()
    tasks = db.query(Task).filter(Task.user_id == user.id).order_by(Task.plan_date, Task.id).all()
    return Response(
        content=export_calendar(exams, tasks, user.id),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="fmzh_{beijing_day():%Y%m%d}.ics"'},
    )
