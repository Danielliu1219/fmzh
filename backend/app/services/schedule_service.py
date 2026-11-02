"""日程服务：任务冲突检测（2.8）、倒推生成备考时间表（2.7）、ICS 解析（2.12）

被 tasks / exams 路由共用；冲突口径：同一天任务总时长超过上限时提醒（README §2 用例 2.8）。
"""
from .pressure import beijing_day
import json
from collections import Counter
from datetime import date, timedelta

from sqlalchemy.orm import Session

from ..models.models import Analysis, Exam, Task, Reminder, Notification
from .task_conflicts import lock_schedule
from .study_planner import daily_budget

# 同一天任务总时长默认上限（分钟），超过即触发提醒
DEFAULT_DAILY_LIMIT_MINUTES = 480


def day_total_minutes(
    db: Session, user_id: int, plan_date: date, exclude_task_id: int | None = None
) -> int:
    """某用户某天已有任务的预计时长总和（已完成的也计入，仍占用当天时间）"""
    query = db.query(Task).filter(Task.user_id == user_id, Task.plan_date == plan_date)
    if exclude_task_id:
        query = query.filter(Task.id != exclude_task_id)
    return sum(task.estimated_minutes or 0 for task in query.all())


def check_conflict(
    db: Session,
    user_id: int,
    plan_date: date,
    estimated_minutes: int,
    exclude_task_id: int | None = None,
    daily_limit_minutes: int = DEFAULT_DAILY_LIMIT_MINUTES,
) -> dict:
    """冲突检测：返回 {conflict, date, existing_minutes, planned_minutes, limit_minutes}"""
    existing = day_total_minutes(db, user_id, plan_date, exclude_task_id)
    planned = existing + estimated_minutes
    return {
        "conflict": planned > daily_limit_minutes,
        "date": plan_date.isoformat(),
        "existing_minutes": existing,
        "planned_minutes": planned,
        "limit_minutes": daily_limit_minutes,
    }


def _estimate_total_minutes(db: Session, user_id: int, exam: Exam, daily_minutes: int, available_days=None) -> int:
    """估算该科总复习时长：优先用最新 AI 分析的按天计划合计（大模型估算），
    没有分析结果时按「每日可用时长 × 剩余天数」兜底估算。"""
    analysis = (
        db.query(Analysis)
        .filter(Analysis.user_id == user_id, Analysis.exam_id == exam.id)
        .order_by(Analysis.id.desc())
        .first()
    )
    if analysis:
        try:
            result = json.loads(analysis.result_json or "{}")
            total = sum(
                int(item.get("estimated_minutes") or 0)
                for item in result.get("review_plan", [])
                if isinstance(item, dict)
            )
            if total > 0:
                return total
        except (ValueError, TypeError):
            pass  # 分析结果解析失败则走兜底估算
    days = available_days if available_days is not None else max((exam.exam_date - beijing_day()).days, 1)
    return daily_minutes * days


def generate_schedule(
    db: Session,
    user_id: int,
    exam: Exam,
    daily_minutes: int,
    start_date: date | None = None,
    daily_limit_minutes: int = DEFAULT_DAILY_LIMIT_MINUTES,
) -> dict:
    """按考试日期倒推生成备考时间表（2.7）。

    先按全科共享预算计算候选，容量不足时不修改任何任务。
    完成记录、固定时段和其他科目的任务保留；验证后原子替换旧倒推任务。
    """
    exam_id = exam.id
    lock_schedule(db, user_id)
    exam = db.query(Exam).filter(Exam.id == exam_id, Exam.user_id == user_id).first()
    if exam is None:
        raise ValueError('考试不存在或已删除，请刷新后重试')
    end_date = exam.exam_date - timedelta(days=1)  # 考试前一天为最后复习日
    if end_date < beijing_day():
        raise ValueError("考试日期已过或就是今天，没有可安排的复习时间")
    if start_date is None:
        start_date = beijing_day() + timedelta(days=1)
    start_date = max(start_date, beijing_day())
    if start_date > end_date:
        start_date = end_date
    if (end_date-start_date).days > 365:
        raise ValueError('倒推规划范围最多一年，请调整开始日期')

    budget = daily_budget(db, user_id)
    per_day = min(daily_minutes, budget)
    total_minutes = _estimate_total_minutes(db, user_id, exam, per_day, (end_date-start_date).days+1)
    retained = db.query(Task).filter(
        Task.user_id == user_id, Task.exam_id == exam.id, Task.source == "ai",
        Task.title.like("【倒推】%"),
        (Task.is_done.is_(True) | Task.start_time.is_not(None)),
    ).all()
    total_minutes = max(0, total_minutes - sum(task.estimated_minutes for task in retained))
    days: list[date] = []
    cur = start_date
    while cur <= end_date:
        days.append(cur)
        cur += timedelta(days=1)

    replace_query = db.query(Task).filter(Task.user_id == user_id, Task.exam_id == exam.id,
        Task.source == 'ai', Task.title.like('【倒推】%'), Task.is_done.is_(False), Task.start_time.is_(None))
    replaced_ids = {row.id for row in replace_query.all()}
    retained_rows = [row for row in db.query(Task).filter(Task.user_id == user_id).all() if row.id not in replaced_ids]
    load = Counter()
    for row in retained_rows:
        load[row.plan_date] += row.estimated_minutes or 0

    # 倒推分配：从最后一天向前铺，每天不超过 daily_minutes
    quotas = [0] * len(days)
    remain = total_minutes
    for i in range(len(days) - 1, -1, -1):
        take = min(per_day, max(0, budget-load[days[i]]), remain)
        quotas[i] = take
        remain -= take
        if remain <= 0:
            break
    conflicts: list[dict] = []
    from .task_conflicts import find_overlaps
    for overlap in find_overlaps([t for t in retained_rows if start_date <= t.plan_date <= end_date]):
        conflicts.append(dict(date=overlap['date'], reason=overlap['reason'], existing_minutes=load[date.fromisoformat(overlap['date'])], limit_minutes=budget))
    if remain:
        conflicts.append(dict(date=start_date.isoformat(), existing_minutes=load[start_date],
            planned_minutes=load[start_date]+remain, limit_minutes=budget, minutes=remain,
            reason=f'考试前共享预算不足，仍有{remain}分钟无法安排；原计划已保留'))
    if conflicts:
        db.rollback()
        return dict(created=0, total_minutes=total_minutes, start_date=start_date.isoformat(), end_date=end_date.isoformat(), conflicts=conflicts)

    # 所有候选已通过；删除旧任务的提醒/通知与替换任务属于同一事务。
    for model in (Reminder, Notification):
        db.query(model).filter(model.user_id == user_id, model.target_type == 'task', model.target_id.in_(replaced_ids)).delete(synchronize_session=False)
    replace_query.delete(synchronize_session=False)
    created = 0
    n = len(days)
    for i, (day, minutes) in enumerate(zip(days, quotas)):
        if minutes <= 0:
            continue
        days_left = n - i  # 距考试（含当天）
        priority = 1 if days_left <= 2 else (2 if days_left <= 5 else 3)
        db.add(
            Task(
                user_id=user_id,
                exam_id=exam.id,
                title=f"【倒推】{exam.subject} 第{i + 1}天：复习冲刺（约{minutes}分钟）",
                plan_date=day,
                estimated_minutes=minutes,
                priority=priority,
                sort_order=i,
                source="ai",
            )
        )
        created += 1
    db.commit()
    return {
        "created": created,
        "total_minutes": total_minutes,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "conflicts": conflicts,
    }


# ==================== ICS 解析（2.12） ====================


def parse_ics(text: str) -> list[dict]:
    """兼容原调用方，标准日历解析由 calendar_io 负责。"""
    from .calendar_io import parse_events
    events, _ = parse_events(text)
    return [{**item, "day": date.fromisoformat(item["day"])} for item in events]
