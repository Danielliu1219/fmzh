"""日历单项移动：保持分钟数，检查旧快照，账号写锁内重验并提交。"""
from datetime import time

from fastapi import HTTPException

from ..models.models import Task
from .study_planner import daily_budget
from .task_conflicts import detect_candidates, lock_schedule, schedule_changed
from .task_details import DETAIL_FIELDS, move_fingerprint
from .task_service import normalize_fields, own_exam, own_task, reject_overlaps


def prepare_move(db, user_id, task, payload):
    if payload.fingerprint != move_fingerprint(task):
        raise HTTPException(409, dict(code='stale_task', message='任务已在其他页面修改，请刷新后重新移动'))
    if task.is_done:
        raise HTTPException(409, dict(code='completed_task', message='已完成任务保留历史安排，不能拖动'))
    fields = {key: getattr(task, key) for key in ('exam_id', 'title', 'plan_date', 'estimated_minutes', 'priority', *DETAIL_FIELDS)}
    fields['plan_date'] = payload.plan_date
    if 'start_time' in payload.model_fields_set:
        start = payload.start_time
        if start is None:
            fields['start_time'] = fields['end_time'] = None
        else:
            end_minutes = start.hour*60 + start.minute + task.estimated_minutes
            if end_minutes > 1439:
                raise HTTPException(422, '该时段会跨越午夜，请选择更早的时间或先拆分任务')
            fields['start_time'], fields['end_time'] = start, time(end_minutes//60, end_minutes%60)
    fields = normalize_fields(fields)
    exam = own_exam(db, user_id, task.exam_id)
    if fields['plan_date'] > exam.exam_date:
        raise HTTPException(422, '任务日期不能晚于考试日期')
    changed = schedule_changed(task, fields)
    overlaps = detect_candidates(db, user_id, [fields], task.id) if changed else []
    existing = sum(t.estimated_minutes for t in db.query(Task).filter(
        Task.user_id == user_id, Task.plan_date == payload.plan_date, Task.id != task.id).all())
    planned, limit = existing + task.estimated_minutes, daily_budget(db, user_id)
    return dict(candidate=fields, overlaps=overlaps, can_save=not overlaps, changed=changed,
                budget_exceeded=planned > limit, existing_minutes=existing, planned_minutes=planned, limit_minutes=limit)


def preview_move(db, user_id, task_id, payload):
    return prepare_move(db, user_id, own_task(db, user_id, task_id), payload)


def apply_move(db, user_id, task_id, payload):
    try:
        lock_schedule(db, user_id)
        task = own_task(db, user_id, task_id, lock=True)
        preview = prepare_move(db, user_id, task, payload)
        reject_overlaps(preview['overlaps'])
        if preview['changed'] and preview['budget_exceeded'] and not payload.allow_over_budget:
            raise HTTPException(409, dict(code='daily_budget_exceeded', message='目标日期超过全科日预算，请先确认取舍',
                                         existing_minutes=preview['existing_minutes'], planned_minutes=preview['planned_minutes'], limit_minutes=preview['limit_minutes']))
        candidate = preview['candidate']
        if task.repeat_group_id and task.plan_date != candidate['plan_date']:
            task.repeat_group_id, task.repeat_rule, task.repeat_until = None, 'none', None
        for key in ('plan_date', 'start_time', 'end_time'):
            setattr(task, key, candidate[key])
        db.commit()
        db.refresh(task)
        return task
    except Exception:
        db.rollback()
        raise
