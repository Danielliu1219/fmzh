"""复习计划落库：把 AI 生成的 review_plan 转成 tasks 表记录"""
from datetime import date, timedelta

from sqlalchemy.orm import Session

from ..models.models import Task


def create_tasks_from_plan(
    db: Session, user_id: int, exam_id: int, analysis_id: int, plan_items: list
) -> int:
    """删除该考试旧的 AI 任务，按新计划重建，返回任务数量"""
    db.query(Task).filter(Task.exam_id == exam_id, Task.source == "ai").delete()

    today = date.today()
    count = 0
    for i, item in enumerate(plan_items):
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
                estimated_minutes=int(item.estimated_minutes or 60),
                priority=int(item.priority or 2),
                sort_order=i,
                source="ai",
            )
        )
        count += 1
    db.commit()
    return count
