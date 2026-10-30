"""学习反馈重排：保持未完成工作量，按全科预算预览；确认时校验快照并原子保存。"""
import hashlib
import json
from copy import deepcopy
from datetime import date

from fastapi import HTTPException

from ..models.models import Analysis, Collection, Exam, QuizAttempt, Task, User
from ..schemas.schemas import AnalysisResult, PlanItem, ReplanOut, WeightChange
from . import study_planner
from .mistakes import normalized_title
from .recommendation_strategy import refresh_strategy
from .task_details import SNAPSHOT_FIELDS


def feedback(db, user_id, exam_id):
    attempts = db.query(QuizAttempt).filter(
        QuizAttempt.user_id == user_id, QuizAttempt.exam_id == exam_id,
        QuizAttempt.status == 'submitted',
    ).order_by(QuizAttempt.submitted_at.desc(), QuizAttempt.id.desc()).limit(20).all()
    latest = {}
    for attempt in attempts:
        try:
            items = json.loads(attempt.result_json or '{}').get('items', [])
        except (ValueError, AttributeError):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            key = normalized_title(str(item.get('question') or ''))
            if key and key not in latest:
                latest[key] = item
    counts = {}
    for item in latest.values():
        name = str(item.get('knowledge_point') or '').strip()
        if name and not item.get('correct'):
            counts[name] = counts.get(name, 0) + 1
    legacy = []
    if not attempts:
        # 无科目标识的历史错题不能串入任意其他课程。
        rows = db.query(Collection).filter(Collection.user_id == user_id, Collection.source == 'quiz', Collection.item_type == 'question').all()
        for row in rows:
            try:
                item = json.loads(row.content or '{}')
            except ValueError:
                continue
            if isinstance(item, dict) and item.get('exam_id') == exam_id:
                name = str(item.get('knowledge_point') or '').strip()
                if name:
                    counts[name] = counts.get(name, 0) + 1
                    legacy.append([row.id, row.content])
    evidence = [[a.id, a.result_json] for a in attempts] + legacy
    return counts, evidence


def _matching(name, counts):
    return sum(n for key, n in counts.items() if key == name or (len(key) >= 3 and (key in name or name in key)))


def snapshot(db, user, exam_id):
    exam = db.query(Exam).filter(Exam.id == exam_id, Exam.user_id == user.id).first()
    if exam is None:
        raise HTTPException(404, '考试不存在')
    if exam.exam_date < date.today():
        raise HTTPException(409, '该考试已经结束，不能再安排备考任务')
    analysis = db.query(Analysis).filter(Analysis.user_id == user.id, Analysis.exam_id == exam_id).order_by(Analysis.id.desc()).first()
    if analysis is None:
        raise HTTPException(404, '该科目还没有分析结果')
    try:
        data = json.loads(analysis.result_json)
        result = AnalysisResult.model_validate(data)
    except ValueError:
        raise HTTPException(500, '历史分析数据损坏')
    rows = db.query(Task).filter(Task.user_id == user.id).order_by(Task.id).all()
    own = [t for t in rows if t.exam_id == exam_id and t.source == 'ai']
    done = sum(t.is_done for t in own)
    rate = done / len(own) if own else 0.0
    wrong, evidence = feedback(db, user.id, exam_id)
    feedback_key = hashlib.sha256(json.dumps(evidence, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    days_left = (exam.exam_date - date.today()).days
    # 反馈始终叠加在分析的原始权重上，重复点击不会反复抬高同一错题的权重。
    base = data.get('replan_base_weights') or {kp.name: kp.weight for kp in result.knowledge_points}
    changes = []
    for kp in result.knowledge_points:
        weight = float(base.get(kp.name, kp.weight))
        reasons = []
        errors = _matching(kp.name, wrong)
        if errors:
            weight += min(0.3, errors * 0.08)
            reasons.append(f'最近自测仍有 {errors} 道错题，优先巩固')
        if own and rate < 0.5 and base.get(kp.name, kp.weight) >= 0.6:
            weight += 0.03
            reasons.append('任务完成率较低，优先保留重要内容')
        if days_left <= 3 and base.get(kp.name, kp.weight) < 0.6 and not errors:
            weight -= 0.08
            reasons.append('临近考试，低权重内容后置')
        changes.append(WeightChange(name=kp.name, old_weight=kp.weight, new_weight=round(max(0.05, min(1.0, weight)), 2), reason='；'.join(reasons) or '保持原始权重'))
    changes.sort(key=lambda c: c.new_weight, reverse=True)
    priorities = {}
    tasks = []
    for task in rows:
        item = {k: getattr(task, k) for k in SNAPSHOT_FIELDS}
        if task.exam_id == exam_id and task.source == 'ai' and not task.is_done:
            matches = [c.new_weight for c in changes if c.name in task.title or task.title in c.name]
            if matches:
                weight = max(matches)
                item['priority'] = 1 if weight >= 0.7 else 2 if weight >= 0.45 else 3
                priorities[task.id] = item['priority']
        tasks.append(item)
    additions = []
    if evidence and feedback_key != data.get('replan_feedback_key'):
        for change in changes:
            title = f'专项练习：{change.name}'[:256]
            if _matching(change.name, wrong) and not any(t.title == title and not t.is_done for t in own):
                additions.append(dict(id=-len(additions)-1, user_id=user.id, exam_id=exam_id, analysis_id=analysis.id, title=title, plan_date=date.today(), estimated_minutes=30, priority=1, sort_order=len(own)+len(additions), source='ai', is_done=False))
    tasks.extend(additions)
    exams = {e.id: {'exam_date': e.exam_date, 'subject': e.subject} for e in db.query(Exam).filter(Exam.user_id == user.id).all()}
    budget = study_planner.daily_budget(db, user.id)
    scheduling = study_planner.distribute(tasks, exams, budget, date.today())
    fingerprint = hashlib.sha256(json.dumps([date.today(), budget, tasks, exams, analysis.id, data, evidence], ensure_ascii=False, default=str, sort_keys=True).encode()).hexdigest()
    scheduling['fingerprint'] = fingerprint
    priority_map = {t['id']: t['priority'] for t in tasks}
    plan = [PlanItem(day=(date.fromisoformat(a['date'])-date.today()).days+1, date=a['date'], title=a['title'], estimated_minutes=a['minutes'], priority=priority_map[a['task_id']], detail='依据当前学习反馈在全科共享预算内调整') for a in scheduling['assignments'] if a['exam_id'] == exam_id]
    plan.extend(PlanItem(day=(t.plan_date-date.today()).days+1, date=t.plan_date.isoformat(), title=t.title,
                        estimated_minutes=t.estimated_minutes, priority=priorities.get(t.id, t.priority),
                        detail=f'保留固定时段 {t.start_time:%H:%M}–{t.end_time:%H:%M}；{t.detail or ""}')
                for t in own if not t.is_done and t.start_time is not None)
    plan.sort(key=lambda p: (p.date, p.priority))
    note = f'剩余 {days_left} 天，任务完成率 {rate:.0%}，最近自测错题 {sum(wrong.values())} 道。保留手动与已完成任务，本次追加 {len(additions)} 项针对性练习（每项 30 分钟），统一校验全科预算。'
    if scheduling['conflicts']:
        note += '容量不足，处理冲突前不能应用。'
    elif not plan:
        note += '本科没有待重排的 AI 任务，不会重复生成已完成的工作。'
    output = ReplanOut(exam_id=exam_id, days_left=days_left, done_tasks=done, total_tasks=len(own), completion_rate=round(rate, 2), wrong_questions=sum(wrong.values()), weights=changes, plan=plan, note=note, fingerprint=fingerprint, scheduling=scheduling)
    return output, analysis, data, base, priorities, additions, feedback_key


def replan(db, user, exam_id, payload):
    if not payload.apply:
        return snapshot(db, user, exam_id)[0]
    if not payload.fingerprint:
        raise HTTPException(409, '请先预览调整，再确认应用')
    try:
        # 先获取写锁，再读取确认所用快照，避免确认过程中其他请求改写任务。
        from .task_conflicts import lock_schedule
        lock_schedule(db, user.id, auth_key=user.auth_key)
        output, analysis, data, base, priorities, additions, feedback_key = snapshot(db, user, exam_id)
        if output.fingerprint != payload.fingerprint:
            raise HTTPException(409, '任务、预算或自测结果已变化，请重新预览')
        if output.scheduling['conflicts']:
            raise HTTPException(409, '任务无法在考试前的全科预算内排完，请先调整任务或预算')
        for task_id, priority in priorities.items():
            db.query(Task).filter(Task.id == task_id, Task.user_id == user.id).update({Task.priority: priority}, synchronize_session=False)
        scheduling = deepcopy(output.scheduling)
        for job in additions:
            temporary_id = job['id']
            task = Task(**{k: v for k, v in job.items() if k != 'id'})
            db.add(task)
            db.flush()
            for assignment in scheduling['assignments']:
                if assignment['task_id'] == temporary_id:
                    assignment['task_id'] = task.id
        study_planner.apply(db, user.id, scheduling, commit=False)
        weight_map = {c.name: c.new_weight for c in output.weights}
        for item in data.get('knowledge_points', []):
            if item.get('name') in weight_map:
                item['weight'] = weight_map[item['name']]
        data.setdefault('knowledge_points', []).sort(key=lambda item: item.get('weight', 0), reverse=True)
        data['replan_base_weights'] = base
        data['replan_feedback_key'] = feedback_key
        data['review_plan'] = [p.model_dump() for p in output.plan]
        updated_result = AnalysisResult.model_validate(data)
        refresh_strategy(updated_result)
        data.update(updated_result.model_dump(mode='json'))
        analysis.result_json = json.dumps(data, ensure_ascii=False)
        db.flush()
        output.task_count = db.query(Task).filter(Task.user_id == user.id, Task.exam_id == exam_id, Task.source == 'ai', Task.is_done.is_(False)).count()
        db.commit()
        output.applied = True
        output.note += '已确认应用，计划与权重同时保存。'
        return output
    except Exception:
        db.rollback()
        raise
