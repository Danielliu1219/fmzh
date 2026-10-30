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


def lock_schedule(db, user_id, *, auth_key=None):
    """变更前取得账号锁；重读数据库状态，直到调用者提交或回滚才释放。"""
    from fastapi import HTTPException
    query = db.query(User).filter(User.id == user_id)
    if auth_key is not None:
        query = query.filter(User.auth_key == auth_key)
    if query.update({User.id: user_id}, synchronize_session=False) != 1:
        raise HTTPException(401, '登录已失效，请重新登录')
    # 等待锁期间其他事务可能已提交；不能沿用Session中预先读取的旧对象。
    # 调用者必须先锁后改，避免expire_all丢弃尚未flush的字段修改。
    db.expire_all()
