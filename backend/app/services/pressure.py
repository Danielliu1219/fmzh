"""实时压力公式与每日记录读取；每日任务复用同一公式，不改权重或分档。"""
import json
from datetime import datetime, timedelta, timezone

from ..models.models import DailyPressure, Exam, Task

BEIJING = timezone(timedelta(hours=8))
FORMULA_VERSION = 'v1'


def utcnow():
    return datetime.now(timezone.utc)


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def beijing_day(value=None):
    return utc(value or utcnow()).astimezone(BEIJING).date()


def _exam_density(exams, today):
    upcoming = [e for e in exams if 0 <= (e.exam_date - today).days <= 7]
    return min(1.0, len(upcoming) / 4)


def _task_rates(tasks, today):
    total = len(tasks)
    if total == 0:
        return 0.0, 0.0
    done = sum(1 for t in tasks if t.is_done)
    overdue = sum(1 for t in tasks if not t.is_done and t.plan_date < today)
    return overdue / total, done / total


def _exam_proximity(exams, today):
    future = [e for e in exams if e.exam_date >= today]
    if not future:
        return 0.0
    days_left = min((e.exam_date - today).days for e in future)
    if days_left <= 0:
        return 1.0
    return min(1.0, 21 / days_left)


def _level_of(score):
    if score < 40:
        return '轻松', '状态不错，按计划推进即可'
    if score < 60:
        return '适中', '压力适中，保持当前节奏'
    if score < 80:
        return '偏压', '压力偏高，建议开启临时救急模式'
    return '高压', '压力很高，建议减负并优先攻坚高频考点'


def calculate(exams, tasks, today):
    density = _exam_density(exams, today)
    backlog, done_rate = _task_rates(tasks, today)
    proximity = _exam_proximity(exams, today)
    score = round(30 * density + 30 * backlog + 20 * (1 - done_rate) + 20 * proximity, 1)
    level, suggestion = _level_of(score)
    return dict(score=score, level=level, suggestion=suggestion,
                breakdown=dict(exam_density=round(density, 3), task_backlog=round(backlog, 3),
                               task_done_rate=round(done_rate, 3), exam_proximity=round(proximity, 3)),
                need_emergency=score >= 60)


def compute_pressure(db, user_id, today=None):
    exams = db.query(Exam).filter(Exam.user_id == user_id).all()
    tasks = db.query(Task).filter(Task.user_id == user_id).all()
    return calculate(exams, tasks, today or beijing_day())


def record_out(row):
    level, suggestion = _level_of(row.score)
    return dict(score=row.score, level=level, suggestion=suggestion, breakdown=json.loads(row.breakdown),
                need_emergency=row.score >= 60, record_date=row.record_date,
                computed_at=utc(row.computed_at), source=row.source, formula_version=row.formula_version)


def current_pressure(db, user_id):
    now = utcnow()
    today = beijing_day(now)
    row = db.query(DailyPressure).filter(DailyPressure.user_id == user_id, DailyPressure.record_date == today).first()
    return {**compute_pressure(db, user_id, today), 'date':today, 'computed_at':utc(now),
            'timezone':'Asia/Shanghai', 'daily_snapshot':record_out(row) if row else None,
            'daily_status':'ready' if row else 'pending'}


def history(db, user_id, days):
    end = beijing_day()
    start = end-timedelta(days=days-1)
    rows = db.query(DailyPressure).filter(DailyPressure.user_id == user_id, DailyPressure.record_date >= start,
                                        DailyPressure.record_date <= end).order_by(DailyPressure.record_date.desc()).all()
    available = {row.record_date for row in rows}
    return dict(window_start=start, window_end=end, timezone='Asia/Shanghai', scheduled_time='00:05',
                items=[record_out(row) for row in rows],
                missing_dates=[start+timedelta(days=i) for i in range(days) if start+timedelta(days=i) not in available],
                note='仅显示实际自动记录；无记录日期不补造历史分数。每日记录保留计算当时状态，当前压力仍实时更新。')
