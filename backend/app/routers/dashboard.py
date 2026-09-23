"""首页聚合与统计接口"""
import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.models import Analysis, Exam, Task, User
from ..schemas.schemas import DailyStat, DashboardOut, ExamDashboard, StatsOut
from ..utils.security import get_current_user

router = APIRouter()


def _days_left(exam_date: date) -> int:
    return max((exam_date - date.today()).days, 0)


@router.get("/dashboard", response_model=DashboardOut, summary="首页聚合：倒计时 + 今日待办 + 总进度")
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    exams = (
        db.query(Exam).filter(Exam.user_id == user.id).order_by(Exam.exam_date).all()
    )
    today_tasks = (
        db.query(Task)
        .filter(Task.user_id == user.id, Task.plan_date == date.today())
        .order_by(Task.is_done, Task.priority, Task.sort_order, Task.id)
        .all()
    )

    # 各科任务完成情况
    totals = dict(
        db.query(Task.exam_id, func.count(Task.id))
        .filter(Task.user_id == user.id)
        .group_by(Task.exam_id)
        .all()
    )
    dones = dict(
        db.query(Task.exam_id, func.count(Task.id))
        .filter(Task.user_id == user.id, Task.is_done.is_(True))
        .group_by(Task.exam_id)
        .all()
    )

    exam_list = []
    for exam in exams:
        total = totals.get(exam.id, 0)
        done = dones.get(exam.id, 0)
        exam_list.append(
            ExamDashboard(
                id=exam.id,
                subject=exam.subject,
                exam_date=exam.exam_date,
                days_left=_days_left(exam.exam_date),
                location=exam.location,
                duration_minutes=exam.duration_minutes,
                total_tasks=total,
                done_tasks=done,
                progress=round(done / total, 3) if total else 0.0,
            )
        )

    total_all = sum(totals.values())
    done_all = sum(dones.values())
    overall = {
        "total": total_all,
        "done": done_all,
        "rate": round(done_all / total_all, 3) if total_all else 0.0,
    }
    return DashboardOut(exams=exam_list, today_tasks=today_tasks, overall=overall)


@router.get("/stats/{exam_id}", response_model=StatsOut, summary="单科统计：完成率 + 每日情况 + 知识点权重")
def exam_stats(
    exam_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exam = db.query(Exam).filter(Exam.id == exam_id, Exam.user_id == user.id).first()
    if exam is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="考试不存在")

    tasks = (
        db.query(Task)
        .filter(Task.user_id == user.id, Task.exam_id == exam_id)
        .order_by(Task.plan_date)
        .all()
    )
    total = len(tasks)
    done = sum(1 for t in tasks if t.is_done)

    # 按日期聚合
    by_date: dict[str, DailyStat] = {}
    for t in tasks:
        key = t.plan_date.isoformat()
        stat = by_date.setdefault(key, DailyStat(date=key, total=0, done=0))
        stat.total += 1
        if t.is_done:
            stat.done += 1

    # 最新一次分析的知识点权重
    analysis = (
        db.query(Analysis)
        .filter(Analysis.user_id == user.id, Analysis.exam_id == exam_id)
        .order_by(Analysis.id.desc())
        .first()
    )
    knowledge_points = []
    if analysis:
        try:
            result = json.loads(analysis.result_json)
            knowledge_points = [
                {"name": kp.get("name", ""), "weight": kp.get("weight", 0)}
                for kp in result.get("knowledge_points", [])
            ]
        except json.JSONDecodeError:
            pass

    return StatsOut(
        exam_id=exam_id,
        subject=exam.subject,
        days_left=_days_left(exam.exam_date),
        total_tasks=total,
        done_tasks=done,
        rate=round(done / total, 3) if total else 0.0,
        by_date=list(by_date.values()),
        knowledge_points=knowledge_points,
    )
