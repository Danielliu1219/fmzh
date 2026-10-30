"""跨科时间统筹：固定已完成/手动任务，按截止日和需求量分配未完成 AI 任务。"""
import hashlib
import json
import re
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy.orm import Session

from ..models.models import Exam, StudySetting, Task, UserProfile
from .task_details import DETAIL_FIELDS, SNAPSHOT_FIELDS
from .task_conflicts import find_overlaps


def daily_budget(db: Session, user_id: int) -> int:
    setting = db.get(StudySetting, user_id)
    if setting:
        return setting.daily_minutes
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).order_by(UserProfile.id.desc()).first()
    return max(30, min(960, round(profile.daily_hours * 60))) if profile and profile.daily_hours else 240


def distribute(tasks: list[dict], exams: dict, budget: int, today: date) -> dict:
    """纯计算，无副作用。超长任务可跨天拆分；绝不丢弃工作量或越过考试日。"""
    fixed = defaultdict(int)
    jobs = []
    conflicts = [dict(task_id=o['second']['task_id'], title=o['second']['title'], date=o['date'],
                      reason=f"固定时段重叠 {o['start_time']}–{o['end_time']}：{o['first']['title']} 与 {o['second']['title']}")
                 for o in find_overlaps([t for t in tasks if str(t['plan_date']) >= today.isoformat()])]
    for task in tasks:
        day = date.fromisoformat(str(task['plan_date']))
        minutes = max(0, int(task['estimated_minutes'] or 0))
        if task['is_done'] or task['source'] != 'ai' or task.get('start_time') is not None:
            fixed[day] += minutes
            if task.get('start_time') is not None and not task['is_done'] and day < today:
                conflicts.append({'task_id': task['id'], 'title': task['title'], 'minutes': minutes, 'reason': '固定时段已过，请手动改期或打卡；系统不会自动移动固定时段'})
            continue
        exam = exams.get(task['exam_id'])
        deadline = date.fromisoformat(str(exam['exam_date'])) if exam else today - timedelta(days=1)
        # 考试当天不安排新的备考任务；考试就在今天时保留今天最后的复习机会。
        deadline = max(today, deadline - timedelta(days=1)) if deadline >= today else deadline
        jobs.append({**task, 'remaining': minutes, 'deadline': deadline, 'allocations': {}})
    for day, minutes in fixed.items():
        if day >= today and minutes > budget:
            conflicts.append({'date': day.isoformat(), 'minutes': minutes - budget, 'reason': '已完成与手动任务已超过当日预算，请先调整手动任务或预算'})
    # 规划最多一年，防止异常远期日期导致无界计算。
    end = min(max([j['deadline'] for j in jobs] + [d for d in fixed if d >= today], default=today), today + timedelta(days=365))
    day = today
    while day <= end:
        capacity = max(0, budget - fixed[day])
        active = [j for j in jobs if j['remaining'] and j['deadline'] >= day]
        by_subject = defaultdict(int)

        def take(job, minutes):
            amount = min(minutes, job['remaining'])
            if amount <= 0:
                return 0
            job['allocations'][day.isoformat()] = job['allocations'].get(day.isoformat(), 0) + amount
            job['remaining'] -= amount
            by_subject[job['exam_id']] += amount
            return amount

        # 先保障今天必须完成的量：否则即使以后每天排满，也赶不上某个考试。
        for deadline in sorted({j['deadline'] for j in active}):
            due = [j for j in active if j['remaining'] and j['deadline'] <= deadline]
            future_capacity = sum(max(0, budget - fixed[day + timedelta(days=i)]) for i in range(1, (deadline - day).days + 1))
            required = max(0, sum(j['remaining'] for j in due) - future_capacity)
            for job in sorted(due, key=lambda j: (j['deadline'], j['priority'], j['id'])):
                amount = take(job, min(required, capacity))
                required -= amount
                capacity -= amount
                if not required or not capacity:
                    break

        # 余量按各科剩余工作/剩余天数轮转分配，每轮最多 30 分钟。
        # 与按科一次填满整天相比，这样能在同一天兼顾多场考试。
        while capacity:
            active = [j for j in jobs if j['remaining'] and j['deadline'] >= day]
            if not active:
                break
            demand = defaultdict(float)
            for job in active:
                demand[job['exam_id']] += job['remaining'] / max(1, (job['deadline'] - day).days + 1)
            subject = max(demand, key=lambda sid: (demand[sid] / (by_subject[sid] + 30), -sid))
            job = min((j for j in active if j['exam_id'] == subject), key=lambda j: (j['priority'], j['plan_date'], j['id']))
            capacity -= take(job, min(30, capacity))
        day += timedelta(days=1)

    assignments = []
    for job in jobs:
        for day, minutes in sorted(job['allocations'].items()):
            assignments.append({'task_id': job['id'], 'exam_id': job['exam_id'], 'title': job['title'], 'from_date': str(job['plan_date']), 'date': day, 'minutes': minutes})
        if job['remaining']:
            conflicts.append({'task_id': job['id'], 'title': job['title'], 'minutes': job['remaining'], 'reason': '考试前剩余时间不足；请减少任务、增加可用时间或调整目标'})
    totals = defaultdict(int)
    for day, minutes in fixed.items():
        if today <= day <= end:
            totals[day.isoformat()] += minutes
    for assignment in assignments:
        totals[assignment['date']] += assignment['minutes']
    return {'assignments': assignments, 'conflicts': conflicts, 'days': [{'date': d, 'minutes': m} for d, m in sorted(totals.items()) if m > 0], 'daily_minutes': budget}


def preview(db: Session, user_id: int) -> dict:
    today = date.today()
    rows = db.query(Task).filter(Task.user_id == user_id).order_by(Task.id).all()
    tasks = [{key: getattr(t, key) for key in SNAPSHOT_FIELDS} for t in rows]
    exams = {e.id: {'exam_date': e.exam_date, 'subject': e.subject} for e in db.query(Exam).filter(Exam.user_id == user_id).all()}
    budget = daily_budget(db, user_id)
    fingerprint = hashlib.sha256(json.dumps([today, budget, tasks, exams], default=str, sort_keys=True).encode()).hexdigest()
    return {**distribute(tasks, exams, budget, today), 'fingerprint': fingerprint}


def apply(db: Session, user_id: int, plan: dict, *, commit: bool = True):
    if plan['conflicts']:
        raise ValueError('仍有任务无法安排，请先处理冲突')
    grouped = defaultdict(list)
    for item in plan['assignments']:
        grouped[item['task_id']].append(item)
    for task_id, items in grouped.items():
        task = db.query(Task).filter(Task.id == task_id, Task.user_id == user_id, Task.is_done.is_(False), Task.source == 'ai').one()
        title = re.sub(r'（分段 \d+/\d+）$', '', task.title)
        original = {key: getattr(task, key) for key in ('user_id', 'exam_id', 'analysis_id', 'priority', 'sort_order', 'source', *DETAIL_FIELDS)}
        for index, item in enumerate(items):
            row = task if index == 0 else Task(**original)
            row.plan_date = date.fromisoformat(item['date'])
            row.estimated_minutes = item['minutes']
            row.title = title[:235] + (f'（分段 {index + 1}/{len(items)}）' if len(items) > 1 else '')
            if index:
                db.add(row)
    if commit:
        db.commit()
