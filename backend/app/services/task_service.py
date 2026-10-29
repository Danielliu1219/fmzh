"""任务创建/单次编辑/有限重复展开；批量写入与删除均原子提交。"""
from collections import Counter
from uuid import uuid4

from fastapi import HTTPException

from ..models.models import Exam, Notification, Reminder, Task
from ..schemas.schemas import TaskOut
from .study_planner import daily_budget
from .task_details import DETAIL_FIELDS, occurrence_dates, task_time, timed_minutes


def own_exam(db, user_id, exam_id, *, lock=False):
    query = db.query(Exam).filter(Exam.id == exam_id, Exam.user_id == user_id)
    if lock and query.update({Exam.id: exam_id}, synchronize_session=False) != 1:
        raise HTTPException(404, '考试不存在')
    exam = query.populate_existing().first()
    if exam is None:
        raise HTTPException(404, '考试不存在')
    return exam


def own_task(db, user_id, task_id, *, lock=False):
    query = db.query(Task).filter(Task.id == task_id, Task.user_id == user_id)
    if lock and query.update({Task.id: task_id}, synchronize_session=False) != 1:
        raise HTTPException(404, '任务不存在')
    task = query.populate_existing().first()
    if task is None:
        raise HTTPException(404, '任务不存在')
    return task


def normalize_fields(data):
    data = dict(data)
    if any(data.get(key) is None for key in ('exam_id', 'title', 'plan_date', 'estimated_minutes', 'priority', 'location', 'difficulty', 'detail')):
        raise HTTPException(422, '任务的名称、日期、时长、科目、优先级与内容字段不能为null')
    data['title'] = data['title'].strip()
    if not data['title']:
        raise HTTPException(422, '任务名称不能为空')
    try:
        data['start_time'] = task_time(data.get('start_time'))
        data['end_time'] = task_time(data.get('end_time'))
        duration = timed_minutes(data['start_time'], data['end_time'])
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    if duration is not None:
        data['estimated_minutes'] = duration
    return data


def expand(db, user_id, payload, *, lock=False):
    exam = own_exam(db, user_id, payload.exam_id, lock=lock)
    fields = normalize_fields(payload.model_dump(exclude={'exclude_task_id'}))
    until = fields['repeat_until'] or fields['plan_date']
    if until > exam.exam_date:
        raise HTTPException(422, '任务日期和重复截止日不能晚于考试日期')
    try:
        days = occurrence_dates(fields['plan_date'], fields['repeat_rule'], fields['repeat_until'])
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return [{**fields, 'plan_date': day} for day in days]


def preview_tasks(db, user_id, payload):
    if payload.exclude_task_id:
        own_task(db, user_id, payload.exclude_task_id)
        if payload.repeat_rule != 'none':
            raise HTTPException(422, '编辑只影响本次任务，不能在编辑时重新展开重复规则')
    items = expand(db, user_id, payload)
    budget = daily_budget(db, user_id)
    existing = Counter()
    for task in db.query(Task).filter(Task.user_id == user_id).all():
        if task.id != payload.exclude_task_id:
            existing[task.plan_date] += task.estimated_minutes
    added = Counter()
    for item in items:
        added[item['plan_date']] += item['estimated_minutes']
    warnings = [dict(date=day.isoformat(), existing_minutes=existing[day], planned_minutes=existing[day]+minutes,
                     limit_minutes=budget, reason='全科当日总时长超过预算，请确认取舍')
                for day, minutes in sorted(added.items()) if existing[day]+minutes > budget]
    return dict(count=len(items), total_minutes=sum(i['estimated_minutes'] for i in items), items=items, warnings=warnings)


def create_tasks(db, user_id, payload):
    try:
        items = expand(db, user_id, payload, lock=True)
        group = uuid4().hex if payload.repeat_rule != 'none' else None
        tasks = [Task(user_id=user_id, source='manual', repeat_group_id=group, sort_order=i, **item) for i, item in enumerate(items)]
        db.add_all(tasks)
        db.flush()
        ids = [task.id for task in tasks]
        db.commit()
        db.refresh(tasks[0])
        return {**TaskOut.model_validate(tasks[0]).model_dump(), 'created_count': len(tasks), 'created_ids': ids}
    except Exception:
        db.rollback()
        raise


def update_task(db, user_id, task_id, payload):
    try:
        task = own_task(db, user_id, task_id, lock=True)
        changes = payload.model_dump(exclude_unset=True)
        current = {key: getattr(task, key) for key in ('exam_id', 'title', 'plan_date', 'estimated_minutes', 'priority', *DETAIL_FIELDS)}
        data = normalize_fields({**current, **changes})
        exam = own_exam(db, user_id, data['exam_id'], lock=True)
        if (data['plan_date'] != task.plan_date or data['exam_id'] != task.exam_id) and data['plan_date'] > exam.exam_date:
            raise HTTPException(422, '任务日期不能晚于考试日期')
        if task.repeat_group_id and (data['exam_id'] != task.exam_id or data['plan_date'] != task.plan_date):
            # 改期/换科目视为单次例外，避免后续组删除牵连已独立安排的任务。
            task.repeat_group_id, task.repeat_rule, task.repeat_until = None, 'none', None
        for key, value in data.items():
            setattr(task, key, value)
        db.commit()
        db.refresh(task)
        return task
    except Exception:
        db.rollback()
        raise


def delete_tasks(db, user_id, task_id, *, remaining_series=False):
    try:
        task = own_task(db, user_id, task_id, lock=True)
        query = db.query(Task).filter(Task.user_id == user_id)
        if remaining_series:
            if not task.repeat_group_id:
                raise HTTPException(409, '该任务不属于重复任务组')
            query = query.filter(Task.repeat_group_id == task.repeat_group_id, Task.plan_date >= task.plan_date, Task.is_done.is_(False))
        else:
            query = query.filter(Task.id == task.id)
        ids = [t.id for t in query.all()]
        for model in (Reminder, Notification):
            db.query(model).filter(model.user_id == user_id, model.target_type == 'task', model.target_id.in_(ids)).delete(synchronize_session=False)
        db.query(Task).filter(Task.user_id == user_id, Task.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
        return {'ok': True, 'deleted': len(ids)}
    except Exception:
        db.rollback()
        raise
