"""特色功能接口（模块7）：压力指数 / 情绪记录 / 救急模式等
公式口径见 README 第 3.3、3.4 节，实现照抄，不要自行改动。
"""
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.models import Exam, Task, User
from ..schemas.schemas import PressureOut
from ..utils.security import get_current_user

router = APIRouter()


def _exam_density(exams: list[Exam], today: date) -> float:
    """考试密集度 = min(1, 未来 7 天考试场次 ÷ 4); 无考试取 0"""
    upcoming = [e for e in exams if 0 <= (e.exam_date - today).days <= 7]
    return min(1.0, len(upcoming) / 4)


def _task_rates(tasks: list[Task], today: date) -> tuple[float, float]:
    """返回 (任务积压率, 任务完成率); 无任务时均取 0"""
    total = len(tasks)
    if total == 0:
        return 0.0, 0.0
    done = sum(1 for t in tasks if t.is_done)
    overdue = sum(1 for t in tasks if not t.is_done and t.plan_date < today)
    return overdue / total, done / total


def _exam_proximity(exams: list[Exam], today: date) -> float:
    """考试临近度 = min(1, 21 ÷ 最近一场考试剩余天数); 无考试取 0, 考试当天取 1"""
    future = [e for e in exams if e.exam_date >= today]
    if not future:
        return 0.0
    days_left = min((e.exam_date - today).days for e in future)
    if days_left <= 0:
        return 1.0
    return min(1.0, 21 / days_left)


def _level_of(score: float) -> tuple[str, str]:
    """分档: <40 轻松 / 40~60 适中 / 60~80 偏压 / ≥80 高压"""
    if score < 40:
        return "轻松", "状态不错，按计划推进即可"
    if score < 60:
        return "适中", "压力适中，保持当前节奏"
    if score < 80:
        return "偏压", "压力偏高，建议开启临时救急模式"
    return "高压", "压力很高，建议减负并优先攻坚高频考点"


def compute_pressure(db: Session, user_id: int) -> dict:
    """压力指数 = 30×考试密集度 + 30×任务积压率 + 20×(1-任务完成率) + 20×考试临近度"""
    today = date.today()
    exams = db.query(Exam).filter(Exam.user_id == user_id).all()
    tasks = db.query(Task).filter(Task.user_id == user_id).all()

    density = _exam_density(exams, today)
    backlog, done_rate = _task_rates(tasks, today)
    proximity = _exam_proximity(exams, today)

    score = round(30 * density + 30 * backlog + 20 * (1 - done_rate) + 20 * proximity, 1)
    level, suggestion = _level_of(score)
    return {
        "score": score,
        "level": level,
        "suggestion": suggestion,
        "breakdown": {
            "exam_density": round(density, 3),
            "task_backlog": round(backlog, 3),
            "task_done_rate": round(done_rate, 3),
            "exam_proximity": round(proximity, 3),
        },
        "need_emergency": score >= 60,
    }


@router.get("/pressure", response_model=PressureOut, summary="期末压力指数")
def pressure(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return compute_pressure(db, user.id)
