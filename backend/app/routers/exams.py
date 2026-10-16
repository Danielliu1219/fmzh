"""考试接口：增删改查（均限定为当前登录用户自己的数据）

考试与日程扩展用例：
- 2.4 筛选查看考试列表（按科目 / 日期区间）
- 2.7 按考试日期倒推生成备考时间表（调用 services/schedule_service）
- 2.12 ICS 导入：解析 ICS 为学习任务，合并前做冲突检测
- 2.13 ICS 导出：考试与任务导出为 ICS 日历文件
"""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.models import Exam, Task, User
from ..schemas.schemas import (
    ExamCreate,
    ExamOut,
    ExamUpdate,
    IcsImportResult,
    ScheduleGenerateOut,
    ScheduleGenerateRequest,
)
from ..services import schedule_service
from ..services.schedule_service import DEFAULT_DAILY_LIMIT_MINUTES, parse_ics
from ..utils.security import get_current_user

router = APIRouter()


def _get_own_exam(db: Session, user: User, exam_id: int) -> Exam:
    exam = db.query(Exam).filter(Exam.id == exam_id, Exam.user_id == user.id).first()
    if exam is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="考试不存在")
    return exam


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
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exam = Exam(user_id=user.id, **payload.model_dump())
    db.add(exam)
    db.commit()
    db.refresh(exam)
    return exam


@router.put("/{exam_id}", response_model=ExamOut, summary="修改考试")
def update_exam(
    exam_id: int,
    payload: ExamUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exam = _get_own_exam(db, user, exam_id)
    for field, value in payload.model_dump(exclude_none=True).items():
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
    exam = _get_own_exam(db, user, exam_id)
    db.delete(exam)
    db.commit()
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


@router.post("/import-ics", response_model=IcsImportResult, summary="ICS 导入：解析为学习任务并合并（2.12）")
async def import_ics(
    file: UploadFile = File(...),
    exam_id: int = Form(...),
    daily_limit_minutes: int = Form(DEFAULT_DAILY_LIMIT_MINUTES),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """解析 ICS 文件中的 VEVENT 为该科目学习任务；合并前按天做冲突检测，超限日期在结果中提醒"""
    exam = _get_own_exam(db, user, exam_id)
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("gbk", errors="replace")

    events = parse_ics(text)
    if not events:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="未从文件中解析到有效的日历事件（VEVENT）")

    imported, skipped, conflict_map = 0, 0, {}
    for event in events:
        if not event["title"]:
            skipped += 1
            continue
        existing = schedule_service.day_total_minutes(db, user.id, event["day"])
        if existing + event["minutes"] > daily_limit_minutes:
            info = conflict_map.setdefault(
                event["day"].isoformat(),
                {
                    "date": event["day"].isoformat(),
                    "existing_minutes": existing,
                    "planned_minutes": existing,
                    "limit_minutes": daily_limit_minutes,
                    "titles": [],
                },
            )
            info["planned_minutes"] += event["minutes"]
            info["titles"].append(event["title"])
        db.add(
            Task(
                user_id=user.id,
                exam_id=exam.id,
                title=f"【ICS】{event['title']}",
                plan_date=event["day"],
                estimated_minutes=event["minutes"],
                priority=2,
                sort_order=0,
                source="manual",
            )
        )
        imported += 1
    db.commit()
    return IcsImportResult(imported=imported, skipped=skipped, conflicts=list(conflict_map.values()))


@router.get("/export-ics", summary="ICS 导出：考试与任务导出为日历文件（2.13）")
def export_ics(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exams = db.query(Exam).filter(Exam.user_id == user.id).order_by(Exam.exam_date).all()
    tasks = (
        db.query(Task)
        .filter(Task.user_id == user.id)
        .order_by(Task.plan_date, Task.id)
        .all()
    )
    subject_by_id = {exam.id: exam.subject for exam in exams}

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//fmzh//期末周别慌！//CN",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:期末周别慌！备考日历",
    ]
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")

    def _fmt(day: date, minutes: int) -> tuple[str, str]:
        start = datetime.combine(day, datetime.min.time()) + timedelta(hours=8)
        end = start + timedelta(minutes=minutes)
        return start.strftime("%Y%m%dT%H%M%S"), end.strftime("%Y%m%dT%H%M%S")

    # 考试安排 → 全天事件（考试当天）
    for exam in exams:
        lines += [
            "BEGIN:VEVENT",
            f"UID:exam-{exam.id}-{user.id}@fmzh",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{exam.exam_date.strftime('%Y%m%d')}",
            f"SUMMARY:【考试】{exam.subject}",
            f"DESCRIPTION:{exam.location or '地点待定'}｜时长 {exam.duration_minutes} 分钟{('｜' + exam.note) if exam.note else ''}",
            "END:VEVENT",
        ]
    # 学习任务 → 按时长生成时间段事件（任务日上午 8 点起）
    for task in tasks:
        start, end = _fmt(task.plan_date, task.estimated_minutes)
        subject = subject_by_id.get(task.exam_id, "")
        lines += [
            "BEGIN:VEVENT",
            f"UID:task-{task.id}-{user.id}@fmzh",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{start}",
            f"DTEND:{end}",
            f"SUMMARY:【任务】{subject + '·' if subject else ''}{task.title}",
            f"DESCRIPTION:{'已完成' if task.is_done else '未完成'}｜预计 {task.estimated_minutes} 分钟",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")

    content = "\r\n".join(lines)
    filename = f"fmzh_{datetime.now().strftime('%Y%m%d')}.ics"
    return Response(
        content=content,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
