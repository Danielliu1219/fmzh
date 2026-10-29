"""复习计划落库：把 AI 生成的 review_plan 转成 tasks 表记录"""
from datetime import date, timedelta
import re
from collections import defaultdict
from sqlalchemy import or_

from sqlalchemy.orm import Session

from ..models.models import Task
from . import study_planner


def create_tasks_from_plan(
    db: Session, user_id: int, exam_id: int, analysis_id: int, plan_items: list
) -> dict:
    """保留完成记录，替换本科未完成 AI 任务；全科容量不足时回滚并返回原因。"""
    transaction = db.begin_nested()
    completed = defaultdict(int)
    for task in db.query(Task).filter(Task.user_id == user_id, Task.exam_id == exam_id, Task.source == 'ai', or_(Task.is_done.is_(True), Task.start_time.is_not(None))).all():
        title = re.sub(r'（分段 \d+/\d+）$', '', task.title)
        completed[title] += task.estimated_minutes
    for old_task in db.query(Task).filter(Task.user_id == user_id, Task.exam_id == exam_id, Task.source == "ai", Task.is_done.is_(False), Task.start_time.is_(None)).all():
        db.delete(old_task)
    db.flush()

    today = date.today()
    count = 0
    for i, item in enumerate(plan_items):
        remaining_minutes = max(0, int(item.estimated_minutes or 60) - completed[item.title])
        if not remaining_minutes:
            continue
        # 日期解析失败时按"今天 + 第 N 天"兜底
        try:
            plan_date = date.fromisoformat(item.date)
        except (ValueError, AttributeError):
            plan_date = today + timedelta(days=max(int(getattr(item, "day", 1)) - 1, 0))

        db.add(
            Task(
                user_id=user_id,
                exam_id=exam_id,
                analysis_id=analysis_id,
                title=item.title,
                plan_date=plan_date,
                estimated_minutes=remaining_minutes,
                detail=(getattr(item, 'detail', '') + '\n' + '\n'.join(f'{a.label} {a.minutes}分钟：{a.detail}' for a in getattr(item, 'activities', []))).strip()[:2000],
                priority=int(item.priority or 2),
                sort_order=i,
                source="ai",
            )
        )
        count += 1
    db.flush()
    plan = study_planner.preview(db, user_id)
    if plan['conflicts']:
        transaction.rollback()
    else:
        study_planner.apply(db, user_id, plan, commit=False)
        transaction.commit()
        db.commit()
    return {'created': count if not plan['conflicts'] else 0, 'applied': not plan['conflicts'], 'conflicts': plan['conflicts']}
