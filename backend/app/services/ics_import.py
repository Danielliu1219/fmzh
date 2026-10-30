"""无写入的签名预览，确认时重新校验并原子保存任务和幂等凭据。"""
import hashlib
import json
from datetime import date, datetime, timedelta, timezone

import jwt
from fastapi import HTTPException

from ..config import settings
from ..models.models import Exam, IcsImportReceipt, Task, User
from .calendar_io import parse_events
from .study_planner import daily_budget, preview as plan_preview
from .task_details import task_time
from .task_conflicts import detect_candidates


def validate(db, user, exam, events, requested_limit=None):
    budget = daily_budget(db, user.id)
    limit = min(budget, requested_limit) if requested_limit is not None else budget
    if not 30 <= limit <= 960:
        raise HTTPException(422, "每日预算需在 30～960 分钟之间")
    totals, additions, conflicts = {}, {}, []
    for task in db.query(Task).filter(Task.user_id == user.id).all():
        key = task.plan_date.isoformat()
        totals[key] = totals.get(key, 0) + task.estimated_minutes
    deadline = max(date.today(), exam.exam_date - timedelta(days=1))
    for event in events:
        day = date.fromisoformat(event['day'])
        if day < date.today() or exam.exam_date < date.today() or day > deadline:
            conflicts.append(dict(date=event['day'], reason="事件不在今天至考前的可复习日期内"))
        additions[event['day']] = additions.get(event['day'], 0) + event['minutes']
    for day, minutes in sorted(additions.items()):
        existing = totals.get(day, 0)
        if existing + minutes > limit:
            conflicts.append(dict(date=day, existing_minutes=existing, planned_minutes=existing + minutes,
                                  limit_minutes=limit, reason="全科每日总时长超出预算"))
    candidates = [{**event, 'plan_date': date.fromisoformat(event['day']), 'exam_id': exam.id} for event in events]
    conflicts.extend({**overlap, 'kind': 'time_overlap'} for overlap in detect_candidates(db, user.id, candidates))
    return limit, conflicts


def preview_import(db, user, exam, text, requested_limit=None):
    try:
        events, skipped = parse_events(text)
    except (ValueError, TypeError, OverflowError) as exc:
        raise HTTPException(400, str(exc))
    events.sort(key=lambda item: (item['day'], item.get('start_time') or '', item['title'], item['minutes'], item.get('end_time') or '', item.get('location', ''), item.get('detail', '')))
    key = hashlib.sha256(json.dumps([user.id, exam.id, exam.created_at.isoformat(), events], sort_keys=True).encode()).hexdigest()
    receipt = db.get(IcsImportReceipt, key)
    legacy_imported = False
    if receipt is None:
        # 旧版本按标题/日期/分钟去重；升级后不把同一旧文件再次插入。
        legacy = {(event['title'], event['day'], event['minutes']) for event in events}
        legacy_events = [dict(title=title, day=day, minutes=minutes) for title, day, minutes in sorted(legacy, key=lambda row: (row[1], row[0], row[2]))]
        legacy_key = hashlib.sha256(json.dumps([user.id, exam.id, exam.created_at.isoformat(), legacy_events], sort_keys=True).encode()).hexdigest()
        receipt = db.get(IcsImportReceipt, legacy_key)
        if receipt is not None:
            key, legacy_imported = legacy_key, True
    limit, conflicts = validate(db, user, exam, events, requested_limit)
    payload = dict(typ='ics_preview', sub=str(user.id), sid=user.auth_key, exam_id=exam.id,
                   events=events, skipped=skipped, limit=requested_limit, import_key=key,
                   fingerprint=plan_preview(db, user.id)['fingerprint'],
                   exp=datetime.now(timezone.utc) + timedelta(minutes=10))
    return dict(imported=0, count=len(events), skipped=skipped, conflicts=conflicts,
                events=events, daily_limit_minutes=limit, already_imported=receipt is not None,
                preview_token=jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256'),
                note=('该文件已按旧版规则导入，不会重复创建；如需补充精确时段，请编辑原任务。' if legacy_imported else
                      '保留北京时间的同日起止时间、地点与说明；全天事件按60分钟、时间待安排导入。预览不保存，10分钟内确认有效。'))


def confirm_import(db, user, token):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'], options={'require': ['sub', 'sid', 'typ', 'exp']})
        if payload['typ'] != 'ics_preview' or payload['sub'] != str(user.id) or payload['sid'] != user.auth_key:
            raise ValueError('wrong preview owner/purpose')
    except (jwt.InvalidTokenError, ValueError, KeyError):
        raise HTTPException(409, "导入预览已失效，请重新选择文件预览")
    try:
        from .task_conflicts import lock_schedule
        lock_schedule(db, user.id, auth_key=user.auth_key)
        receipt = db.get(IcsImportReceipt, payload['import_key'])
        if receipt:
            db.rollback()
            return dict(imported=receipt.imported, skipped=payload['skipped'], conflicts=[], already_imported=True)
        exam = db.query(Exam).filter(Exam.id == payload['exam_id'], Exam.user_id == user.id).first()
        if exam is None:
            raise HTTPException(404, "考试不存在")
        if payload['fingerprint'] != plan_preview(db, user.id)['fingerprint']:
            raise HTTPException(409, "任务、考试或预算已经变化，请重新预览")
        _, conflicts = validate(db, user, exam, payload['events'], payload['limit'])
        if conflicts:
            raise HTTPException(409, "存在时段、预算或考试日期冲突，请调整后重新预览")
        for index, item in enumerate(payload['events']):
            db.add(Task(user_id=user.id, exam_id=exam.id, title='【ICS】' + item['title'],
                        plan_date=date.fromisoformat(item['day']), estimated_minutes=item['minutes'],
                        start_time=task_time(item.get('start_time')), end_time=task_time(item.get('end_time')),
                        location=item.get('location', ''), detail=item.get('detail', ''),
                        source='manual', priority=2, sort_order=index))
        db.add(IcsImportReceipt(id=payload['import_key'], user_id=user.id, exam_id=exam.id, imported=len(payload['events'])))
        db.commit()
        return dict(imported=len(payload['events']), skipped=payload['skipped'], conflicts=[], already_imported=False)
    except Exception:
        db.rollback()
        raise
