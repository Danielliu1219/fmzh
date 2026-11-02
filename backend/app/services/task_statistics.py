"""区间统计按真实打卡时间归属，未知完成时间不伪造成计划日完成。"""

from collections import Counter
from datetime import datetime, time, timedelta
from sqlalchemy import and_, or_
from ..models.models import Task


def window(db, user_id, start, end):
    left = datetime.combine(start, time.min)
    right = datetime.combine(end + timedelta(days=1), time.min)
    tasks = (
        db.query(Task)
        .filter(
            Task.user_id == user_id,
            or_(
                and_(Task.plan_date >= start, Task.plan_date <= end),
                and_(
                    Task.is_done.is_(True), Task.done_at >= left, Task.done_at < right
                ),
            ),
        )
        .all()
    )
    totals, dones, total_days, done_days = Counter(), Counter(), Counter(), Counter()
    unknown = 0
    for task in tasks:
        completed = (
            task.is_done and task.done_at is not None and left <= task.done_at < right
        )
        day = task.done_at.date() if completed else task.plan_date
        totals[task.exam_id] += 1
        total_days[day.isoformat()] += 1
        if completed:
            dones[task.exam_id] += 1
            done_days[day.isoformat()] += 1
        elif task.is_done and task.done_at is None:
            unknown += 1
    return dict(
        total=len(tasks),
        done=sum(dones.values()),
        totals=totals,
        dones=dones,
        total_days=total_days,
        done_days=done_days,
        unknown=unknown,
    )
