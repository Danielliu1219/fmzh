"""同日固定时段交集；区间左闭右开，相接不冲突，未定时任务不推测时间。"""
from collections import defaultdict

from ..models.models import Exam, Task, User
from .task_details import task_time


def value(row, key, default=None):
    return row.get(key, default) if isinstance(row, dict) else getattr(row, key, default)


def schedule_changed(original, proposed):
    return (str(value(original, 'plan_date')) != str(value(proposed, 'plan_date')) or
            any(task_time(value(original, key)) != task_time(value(proposed, key)) for key in ('start_time', 'end_time')))


def find_overlaps(existing, candidates=None, subjects=None):
    subjects = subjects or {}
    days = defaultdict(list)
    for proposed, rows in ((False, existing), (True, candidates or [])):
        for index, row in enumerate(rows):
            start, end = task_time(value(row, 'start_time')), task_time(value(row, 'end_time'))
            if start is None or end is None:
                continue
            exam_id = value(row, 'exam_id')
            item = dict(task_id=None if proposed else value(row, 'id'), candidate_index=index+1 if proposed else None,
                        exam_id=exam_id, subject=subjects.get(exam_id, ''), title=value(row, 'title', '待安排任务'),
                        start_time=start.strftime('%H:%M'), end_time=end.strftime('%H:%M'))
            days[str(value(row, 'plan_date'))].append(item)
    overlaps = []
    for day, rows in sorted(days.items()):
        active = []
        for row in sorted(rows, key=lambda r: (r['start_time'], r['end_time'], r['task_id'] or 0, r['candidate_index'] or 0)):
            active = [previous for previous in active if previous['end_time'] > row['start_time']]
            for previous in active:
                if candidates is not None and not (row['candidate_index'] or previous['candidate_index']):
                    continue
                start, end = max(previous['start_time'], row['start_time']), min(previous['end_time'], row['end_time'])
                minutes = lambda t: int(t[:2])*60+int(t[3:])
                overlaps.append(dict(date=day, start_time=start, end_time=end, overlap_minutes=minutes(end)-minutes(start),
                                     first=previous, second=row, reason='固定时段重叠，请调整其中一项的日期或时间'))
            active.append(row)
    return overlaps


def detect_candidates(db, user_id, items, exclude_task_id=None):
    dates = {value(item, 'plan_date') for item in items}
    rows = db.query(Task).filter(Task.user_id == user_id, Task.plan_date.in_(dates))
    if exclude_task_id is not None:
        rows = rows.filter(Task.id != exclude_task_id)
    subjects = {exam.id: exam.subject for exam in db.query(Exam).filter(Exam.user_id == user_id).all()}
    return find_overlaps(rows.all(), items, subjects)


def lock_schedule(db, user_id):
    # 所有科目创建/改期和 ICS 确认使用同一账号写锁，重验与写入处于同一事务。
    db.query(User).filter(User.id == user_id).update({User.id: user_id}, synchronize_session=False)
