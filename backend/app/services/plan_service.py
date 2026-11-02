"""复习计划落库：把 AI 生成的 review_plan 转成 tasks 表记录"""
from .pressure import beijing_day
from datetime import date, timedelta
import re
from collections import defaultdict
from sqlalchemy import or_

from sqlalchemy.orm import Session
from fastapi import HTTPException

from ..models.models import Exam, Task
from . import study_planner
from .task_conflicts import lock_schedule


def create_tasks_from_plan(
    db: Session, user_id: int, exam_id: int, analysis_id: int, plan_items: list, *, commit: bool = True
) -> dict:
    """保留完成记录，替换本科未完成 AI 任务；全科容量不足时回滚并返回原因。"""
    try:
        lock_schedule(db, user_id)
        if db.query(Exam.id).filter(Exam.id == exam_id, Exam.user_id == user_id).first() is None:
            raise HTTPException(404, '考试不存在或已删除')
        return _replace_tasks(db, user_id, exam_id, analysis_id, plan_items, commit=commit)
    except Exception:
        db.rollback()
        raise


def _replace_tasks(db, user_id, exam_id, analysis_id, plan_items, *, commit):
    if not plan_items:
        raise ValueError("候选复习计划为空，不能替换原计划")
    transaction = db.begin_nested()
    completed = defaultdict(int)
    for task in (
        db.query(Task)
        .filter(
            Task.user_id == user_id,
            Task.exam_id == exam_id,
            Task.source == "ai",
            or_(Task.is_done.is_(True), Task.start_time.is_not(None)),
        )
        .all()
    ):
        title = re.sub(r"（分段 \d+/\d+）$", "", task.title)
        completed[title] += task.estimated_minutes
    candidates = []
    for i, item in enumerate(plan_items):
        minutes = int(item.estimated_minutes or 60)
        credited = min(minutes, completed[item.title])
        completed[item.title] -= credited
        if minutes > credited:
            candidates.append((i, item, minutes - credited))
    old_tasks = (
        db.query(Task)
        .filter(
            Task.user_id == user_id,
            Task.exam_id == exam_id,
            Task.source == "ai",
            Task.is_done.is_(False),
            Task.start_time.is_(None),
        )
        .all()
    )
    if not candidates and old_tasks:
        transaction.rollback()
        if commit:
            db.commit()
        return dict(
            created=0,
            applied=False,
            conflicts=[
                dict(
                    exam_id=exam_id,
                    reason="新内容均已完成或已固定，未产生可执行任务；原未完成计划已保留",
                )
            ],
        )
    for old_task in old_tasks:
        db.delete(old_task)
    db.flush()

    today = beijing_day()
    count = 0
    for i, item, remaining_minutes in candidates:
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
                knowledge_point=getattr(item, "knowledge_point", ""),
                plan_date=plan_date,
                estimated_minutes=remaining_minutes,
                detail=(
                    getattr(item, "detail", "")
                    + "\n"
                    + "\n".join(
                        f"{a.label} {a.minutes}分钟：{a.detail}"
                        for a in getattr(item, "activities", [])
                    )
                ).strip()[:2000],
                priority=int(item.priority or 2),
                sort_order=i,
                source="ai",
            )
        )
        count += 1
    db.flush()
    plan = study_planner.preview(db, user_id)
    if plan["conflicts"]:
        transaction.rollback()
    else:
        study_planner.apply(db, user_id, plan, commit=False)
        transaction.commit()
    if commit:
        db.commit()
    return {
        "created": count if not plan["conflicts"] else 0,
        "applied": not plan["conflicts"],
        "conflicts": plan["conflicts"],
    }
