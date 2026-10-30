"""减负预览与原子确认；保留固定时段、完成历史及工作量，不默默覆盖预览。"""
import hashlib
import json
from datetime import date, datetime, time, timedelta

from fastapi import HTTPException

from ..models.models import Exam, Task
from .study_planner import daily_budget
from .task_conflicts import find_overlaps, lock_schedule
from .task_details import SNAPSHOT_FIELDS, move_fingerprint
from .timeslots import CHINA, local_time


def clock_now():
    return datetime.now(CHINA).replace(tzinfo=None, microsecond=0)


def minute(value):
    return int(value[:2])*60+int(value[3:5])


def hhmm(value):
    return f'{value//60:02d}:{value%60:02d}'


def distribute(tasks, exams, budget, now, option='lighten', half='afternoon'):
    if option not in ('lighten', 'halfday') or half not in ('morning', 'afternoon'):
        raise HTTPException(422, '不支持的减负选项或休息半天')
    today = now.date().isoformat()
    capacity = budget//2
    rest = (0, 720) if half == 'morning' else (720, 1440)
    # 只安排接下来可执行的整分钟，留5分钟供用户确认；23:59后不跨午夜。
    earliest = now.hour*60+now.minute+5+(1 if now.second else 0)
    available = (720, 1439) if half == 'morning' else (0, 720)
    available = (max(available[0], earliest), available[1])
    load, occupied, conflicts, moves = {}, [], [], []
    completed = sum(t['estimated_minutes'] for t in tasks if t['is_done'] and t['plan_date'] == today)
    movable = [t for t in tasks if not t['is_done'] and t['plan_date'] <= today and not t['start_time']]
    frozen = [t for t in tasks if t['is_done'] or t['plan_date'] > today or t['start_time']]

    def issue(task, reason):
        conflicts.append(dict(task_id=task['id'], title=task['title'], reason=reason))

    if option == 'halfday' and half == 'morning' and earliest >= 720:
        conflicts.append(dict(task_id=0, title='休息时段', reason='今日上午已结束，请选择下午休息或明天再规划'))
    for t in frozen:
        day = t['plan_date']
        if day < today:
            if not t['is_done'] and t['start_time']:
                issue(t, '固定时段已过，请先手动改期或打卡')
            continue
        load[day] = load.get(day, 0)+t['estimated_minutes']
        exam = exams.get(t['exam_id'])
        if not t['is_done'] and (not exam or day > str(exam['exam_date'])):
            issue(t, '已有任务晚于考试日或考试不存在，请先调整原安排')
        if day != today or not t['start_time']:
            continue
        a, b = minute(t['start_time']), minute(t['end_time'])
        occupied.append((a,b))
        if not t['is_done'] and option == 'halfday' and a < rest[1] and b > rest[0]:
            issue(t, '固定任务与休息半天重叠，请先在课程管理调整；系统保留原时段')
        elif not t['is_done'] and option == 'halfday' and b <= earliest-5:
            issue(t, '今日固定时段已过，请先手动改期或打卡')
    # 已完成记录只保留，不因其超过减负容量而要求撤销历史。
    if load.get(today, 0) > max(capacity, completed):
        conflicts.append(dict(task_id=0, title='今日固定安排', reason='固定时段与已完成任务已超过减负后的今日容量，请先调整固定时段'))
    for day, used in sorted(load.items()):
        if day > today and used > budget:
            conflicts.append(dict(task_id=0, title=day, reason='已有任务超过全科日预算，请先调整该日安排'))
    for overlap in find_overlaps([t for t in frozen if t['plan_date'] >= today]):
        conflicts.append(dict(task_id=overlap['second']['task_id'] or 0, title=overlap['second']['title'],
                              reason=f"{overlap['date']} 固定时段重叠 {overlap['start_time']}–{overlap['end_time']}，请先调整"))

    def gap(duration):
        cursor = available[0]
        for a,b in sorted(occupied):
            if b <= cursor:
                continue
            if cursor+duration <= min(a, available[1]):
                return cursor
            cursor = max(cursor, b)
        return cursor if cursor+duration <= available[1] else None

    movable.sort(key=lambda t: (t['priority'], str(exams.get(t['exam_id'], {}).get('exam_date', '9999')), t['plan_date'], t['id']))
    for t in movable:
        exam = exams.get(t['exam_id'])
        if not exam:
            issue(t, '考试不存在，请先检查任务归属')
            continue
        deadline = min(date.fromisoformat(str(exam['exam_date'])), now.date()+timedelta(days=365))
        chosen = None
        current = now.date()
        while current <= deadline:
            day = current.isoformat()
            cap = capacity if day == today else budget
            start = None
            if load.get(day, 0)+t['estimated_minutes'] <= cap:
                start = gap(t['estimated_minutes']) if option == 'halfday' and day == today else None
                if option != 'halfday' or day != today or start is not None:
                    chosen = (day, start)
                    break
            current += timedelta(days=1)
        if chosen is None:
            issue(t, '考前容量或连续空档不足；任务整项保留，请减少任务、拆分或增加可用时间')
            continue
        day, start = chosen
        end = start+t['estimated_minutes'] if start is not None else None
        load[day] = load.get(day, 0)+t['estimated_minutes']
        if start is not None:
            occupied.append((start,end))
        a, b = hhmm(start) if start is not None else None, hhmm(end) if end is not None else None
        if day != t['plan_date'] or a != t['start_time'] or b != t['end_time']:
            moves.append(dict(task_id=t['id'], title=t['title'], from_date=t['plan_date'], to_date=day,
                              minutes=t['estimated_minutes'], from_start=t['start_time'], from_end=t['end_time'],
                              to_start=a, to_end=b))
    by_id = {m['task_id']:m for m in moves}
    kept = []
    for t in tasks:
        move = by_id.get(t['id'])
        if not t['is_done'] and (move['to_date'] if move else t['plan_date']) == today:
            kept.append(dict(task_id=t['id'], title=t['title'], minutes=t['estimated_minutes'],
                             start_time=move['to_start'] if move else t['start_time'], end_time=move['to_end'] if move else t['end_time']))
    return dict(option=option, half=half if option == 'halfday' else None, date=today,
                rest_start=hhmm(rest[0]) if option == 'halfday' else None,
                rest_end=hhmm(rest[1]) if option == 'halfday' else None,
                daily_hours=budget/60, daily_minutes=budget, today_capacity=capacity,
                completed_minutes=completed, today_pending_minutes=sum(t['minutes'] for t in kept),
                retained=kept, moves=moves, conflicts=conflicts,
                note='固定任务与已完成历史保持原样；未定时任务按整项安排，不拆分或减少分钟。半天休息仅调整今日计划，不创建长期禁排时段。',
                summary=f'预览含{len(moves)}项调整，{len(conflicts)}项约束需处理' if conflicts else f'确认后调整{len(moves)}项，今日保留{len(kept)}项待办；已完成记录保留')


def preview(db, user_id, option='lighten', half='afternoon', at=None):
    if half not in ('morning', 'afternoon'):
        raise HTTPException(422, '不支持的休息半天')
    if option == 'lighten':
        half = 'afternoon'
    at = local_time(at) if at else clock_now()
    rows = db.query(Task).filter(Task.user_id == user_id).order_by(Task.id).all()
    tasks = [{key: getattr(t,key).isoformat()[:5] if key in ('start_time','end_time') and getattr(t,key) else
              str(getattr(t,key)) if key == 'plan_date' else getattr(t,key) for key in SNAPSHOT_FIELDS} for t in rows]
    exams = {e.id:dict(exam_date=e.exam_date,subject=e.subject) for e in db.query(Exam).filter(Exam.user_id == user_id).all()}
    budget = daily_budget(db,user_id)
    signature = [user_id, at, option, half, budget, [move_fingerprint(t) for t in rows], exams]
    fingerprint = hashlib.sha256(json.dumps(signature,default=str,sort_keys=True).encode()).hexdigest()
    return {**distribute(tasks,exams,budget,at,option,half), 'fingerprint':fingerprint, 'preview_at':at}


def apply(db, user_id, payload):
    try:
        lock_schedule(db,user_id)
        db.expire_all()
        now = clock_now()
        at = local_time(payload.preview_at) if payload.preview_at else None
        if at is None or at > now or now-at > timedelta(minutes=10) or at.date() != now.date():
            raise HTTPException(409, '减负预览已失效，请重新预览后确认')
        plan = preview(db,user_id,payload.option,payload.half,at)
        if payload.fingerprint != plan['fingerprint']:
            raise HTTPException(409, '任务、考试或预算已变化，请重新预览后确认')
        if plan['conflicts']:
            raise HTTPException(409, '仍有约束未解决，请先调整固定安排或每日预算')
        for move in plan['moves']:
            if move['to_start'] and move['to_date'] == now.date().isoformat() and minute(move['to_start']) < now.hour*60+now.minute+(1 if now.second else 0):
                raise HTTPException(409, '预览中的开始时刻已到，请重新预览')
            task = db.query(Task).filter(Task.user_id == user_id,Task.id == move['task_id']).one()
            if task.repeat_group_id and str(task.plan_date) != move['to_date']:
                task.repeat_group_id,task.repeat_rule,task.repeat_until = None,'none',None
            task.plan_date = date.fromisoformat(move['to_date'])
            task.start_time = time.fromisoformat(move['to_start']) if move['to_start'] else None
            task.end_time = time.fromisoformat(move['to_end']) if move['to_end'] else None
        db.commit()
        return plan
    except Exception:
        db.rollback()
        raise
