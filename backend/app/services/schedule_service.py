"""日程服务：任务冲突检测（2.8）、倒推生成备考时间表（2.7）、ICS 解析（2.12）

被 tasks / exams 路由共用；冲突口径：同一天任务总时长超过上限时提醒（README §2 用例 2.8）。
"""
import json
from datetime import date, timedelta

from sqlalchemy.orm import Session

from ..models.models import Analysis, Exam, Task

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


def _estimate_total_minutes(db: Session, user_id: int, exam: Exam, daily_minutes: int) -> int:
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
    days = max((exam.exam_date - date.today()).days, 1)
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

    规则：从开始日到考试前一天，每天安排不超过 daily_minutes 的复习任务，
    越临近考试优先级越高；与现有日程冲突的日期记录下来提醒用户手动调整（不阻止生成）。
    """
    end_date = exam.exam_date - timedelta(days=1)  # 考试前一天为最后复习日
    if end_date < date.today():
        raise ValueError("考试日期已过或就是今天，没有可安排的复习时间")
    if start_date is None:
        start_date = date.today() + timedelta(days=1)
    start_date = max(start_date, date.today())
    if start_date > end_date:
        start_date = end_date

    total_minutes = _estimate_total_minutes(db, user_id, exam, daily_minutes)
    days: list[date] = []
    cur = start_date
    while cur <= end_date:
        days.append(cur)
        cur += timedelta(days=1)

    # 倒推分配：从最后一天向前铺，每天不超过 daily_minutes
    quotas = [0] * len(days)
    remain = total_minutes
    for i in range(len(days) - 1, -1, -1):
        take = min(daily_minutes, remain)
        quotas[i] = take
        remain -= take
        if remain <= 0:
            break
    # 还有剩余且前面有天没排满（总时长超出容量）则均摊补齐
    if remain > 0:
        for i in range(len(days)):
            add = min(remain, daily_minutes - quotas[i])
            quotas[i] += add
            remain -= add
            if remain <= 0:
                break

    # 重建该科倒推任务（与 AI 计划同源：source=ai，重复生成时替换旧任务）
    db.query(Task).filter(
        Task.user_id == user_id,
        Task.exam_id == exam.id,
        Task.source == "ai",
        Task.title.like(f"【倒推】%"),
    ).delete()

    conflicts: list[dict] = []
    created = 0
    n = len(days)
    for i, (day, minutes) in enumerate(zip(days, quotas)):
        if minutes <= 0:
            continue
        # 冲突检测：当天已有任务 + 本任务超过上限时记录提醒
        existing = day_total_minutes(db, user_id, day)
        if existing + minutes > daily_limit_minutes:
            conflicts.append(
                {
                    "date": day.isoformat(),
                    "existing_minutes": existing,
                    "planned_minutes": existing + minutes,
                    "limit_minutes": daily_limit_minutes,
                }
            )
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
