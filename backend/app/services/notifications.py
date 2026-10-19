"""模块 6：仅在显式检查请求时生成到期站内提醒，无定时线程或外部推送。"""
import hashlib
from datetime import datetime, time, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from ..models.models import Exam, Notification, NotificationPreference, Reminder, Task

BEIJING = timezone(timedelta(hours=8))


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso(value):
    return value.replace(tzinfo=timezone.utc).isoformat()


def target(db, user_id, kind, target_id):
    if kind not in ('exam', 'task'):
        raise HTTPException(422, '提醒类型必须为 exam 或 task')
    model = Exam if kind == 'exam' else Task
    row = db.query(model).filter(model.id == target_id, model.user_id == user_id).first()
    if row is None:
        raise HTTPException(404, '考试或任务已不存在')
    if kind == 'task' and db.query(Exam).filter(Exam.id == row.exam_id, Exam.user_id == user_id).first() is None:
        raise HTTPException(404, '任务所属考试已不存在')
    return row


def due_time(row, kind, clock, advance):
    day = row.exam_date if kind == 'exam' else row.plan_date
    event = datetime.combine(day, time.fromisoformat(clock), tzinfo=BEIJING)
    return (event - timedelta(minutes=advance)).astimezone(timezone.utc).replace(tzinfo=None)


def preference(db, user_id):
    row = db.get(NotificationPreference, user_id)
    return {key: getattr(row, key) if row else True for key in ('enabled', 'exam_enabled', 'task_enabled')}


def reminder_data(db, user_id, kind, target_id):
    row = target(db, user_id, kind, target_id)
    rule = db.query(Reminder).filter_by(user_id=user_id, target_type=kind, target_id=target_id).first()
    if rule and rule.target_created_at != row.created_at:
        rule = None
    clock = rule.event_time if rule else '09:00'
    advance = rule.advance_minutes if rule else (1440 if kind == 'exam' else 15)
    return {'target_type': kind, 'target_id': target_id, 'title': row.subject if kind == 'exam' else row.title,
            'event_date': str(row.exam_date if kind == 'exam' else row.plan_date),
            'enabled': rule.enabled if rule else False, 'event_time': clock, 'advance_minutes': advance,
            'due_at': iso(due_time(row, kind, clock, advance)), 'timezone': 'Asia/Shanghai'}


def check_due(db, user_id, now=None):
    now = now or utcnow()
    prefs = preference(db, user_id)
    if not prefs['enabled']:
        return 0
    today = now.replace(tzinfo=timezone.utc).astimezone(BEIJING).date()
    created = 0
    for rule in db.query(Reminder).filter_by(user_id=user_id, enabled=True).all():
        if not prefs[f'{rule.target_type}_enabled']:
            continue
        try:
            row = target(db, user_id, rule.target_type, rule.target_id)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            continue
        if row.created_at != rule.target_created_at:
            continue
        if (rule.target_type == 'task' and row.is_done) or (rule.target_type == 'exam' and row.exam_date < today):
            continue
        due = due_time(row, rule.target_type, rule.event_time, rule.advance_minutes)
        if due > now:
            continue
        key = hashlib.sha256(f'{rule.target_type}:{row.id}:{row.created_at}:{due}'.encode()).hexdigest()
        if db.query(Notification.id).filter_by(user_id=user_id, occurrence_key=key).first():
            continue
        title = row.subject if rule.target_type == 'exam' else row.title
        day = row.exam_date if rule.target_type == 'exam' else row.plan_date
        label = '考试' if rule.target_type == 'exam' else '复习任务'
        try:
            with db.begin_nested():
                db.add(Notification(user_id=user_id, occurrence_key=key, target_type=rule.target_type,
                    target_id=row.id, target_created_at=row.created_at, title=f'{label}提醒 · {title}'[:50],
                    content=f'{title}：{day} {rule.event_time}。已到你设置的提醒时间，请查看安排。'[:200],
                    due_at=due, created_at=now))
                db.flush()
            created += 1
        except IntegrityError:
            # 并发打开页面时由唯一约束保证同一事项同一提醒时间只有一条。
            continue
    db.commit()
    return created


def notification_data(db, user_id, row):
    available = False
    try:
        available = target(db, user_id, row.target_type, row.target_id).created_at == row.target_created_at
    except HTTPException:
        pass
    return {key: getattr(row, key) for key in ('id', 'target_type', 'target_id', 'title', 'content', 'is_read')} | {
        'due_at': iso(row.due_at), 'created_at': iso(row.created_at), 'target_available': available}
