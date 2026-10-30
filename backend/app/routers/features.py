"""特色功能接口（模块7）：压力指数 / 情绪记录 / 救急模式等
公式口径见 README 第 3.3、3.4 节，实现照抄，不要自行改动。
"""
import json
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.models import Analysis, Exam, MoodRecord, Task, User, UserProfile
from ..schemas.schemas import (
    EmergencyOut,
    MoodResult,
    MoodSubmit,
    PressureOut,
    ReliefApply,
    ReliefPlan,
    ReviewOut,
    TimeSlotOut,
    Top3Out,
)
from ..utils.security import get_current_user

router = APIRouter()


def _exam_density(exams: list[Exam], today: date) -> float:
    """考试密集度 = min(1, 未来 7 天考试场次 ÷ 4); 无考试取 0"""
    upcoming = [e for e in exams if 0 <= (e.exam_date - today).days <= 7]
    return min(1.0, len(upcoming) / 4)


def _task_rates(tasks: list[Task], today: date) -> tuple[float, float]:
    """返回 (任务积压率, 任务完成率); 无任务时均取 0"""
    total = len(tasks)
    if total == 0:
        return 0.0, 0.0
    done = sum(1 for t in tasks if t.is_done)
    overdue = sum(1 for t in tasks if not t.is_done and t.plan_date < today)
    return overdue / total, done / total


def _exam_proximity(exams: list[Exam], today: date) -> float:
    """考试临近度 = min(1, 21 ÷ 最近一场考试剩余天数); 无考试取 0, 考试当天取 1"""
    future = [e for e in exams if e.exam_date >= today]
    if not future:
        return 0.0
    days_left = min((e.exam_date - today).days for e in future)
    if days_left <= 0:
        return 1.0
    return min(1.0, 21 / days_left)


def _level_of(score: float) -> tuple[str, str]:
    """分档: <40 轻松 / 40~60 适中 / 60~80 偏压 / ≥80 高压"""
    if score < 40:
        return "轻松", "状态不错，按计划推进即可"
    if score < 60:
        return "适中", "压力适中，保持当前节奏"
    if score < 80:
        return "偏压", "压力偏高，建议开启临时救急模式"
    return "高压", "压力很高，建议减负并优先攻坚高频考点"


def compute_pressure(db: Session, user_id: int) -> dict:
    """压力指数 = 30×考试密集度 + 30×任务积压率 + 20×(1-任务完成率) + 20×考试临近度"""
    today = date.today()
    exams = db.query(Exam).filter(Exam.user_id == user_id).all()
    tasks = db.query(Task).filter(Task.user_id == user_id).all()

    density = _exam_density(exams, today)
    backlog, done_rate = _task_rates(tasks, today)
    proximity = _exam_proximity(exams, today)

    score = round(30 * density + 30 * backlog + 20 * (1 - done_rate) + 20 * proximity, 1)
    level, suggestion = _level_of(score)
    return {
        "score": score,
        "level": level,
        "suggestion": suggestion,
        "breakdown": {
            "exam_density": round(density, 3),
            "task_backlog": round(backlog, 3),
            "task_done_rate": round(done_rate, 3),
            "exam_proximity": round(proximity, 3),
        },
        "need_emergency": score >= 60,
    }


@router.get("/pressure", response_model=PressureOut, summary="期末压力指数")
def pressure(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return compute_pressure(db, user.id)


def _today_completion_rate(db: Session, user_id: int, today: date) -> float:
    """当天的任务完成率（当天无任务取 0）"""
    tasks = db.query(Task).filter(Task.user_id == user_id, Task.plan_date == today).all()
    if not tasks:
        return 0.0
    return sum(1 for t in tasks if t.is_done) / len(tasks)


def _streak_days(db: Session, user_id: int, today: date) -> int:
    """连续达标天数：从今天往前，连续「当天有任务且全部完成」的天数"""
    by_date: dict[date, list[Task]] = {}
    for t in db.query(Task).filter(Task.user_id == user_id).all():
        by_date.setdefault(t.plan_date, []).append(t)
    streak = 0
    cursor = today
    while True:
        day_tasks = by_date.get(cursor)
        if not day_tasks or not all(t.is_done for t in day_tasks):
            break
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def _mood_suggestion(score: float) -> str:
    """复习节奏建议（按综合评分分档）"""
    if score >= 4:
        return "状态很好，可以适当加量，挑战高权重难点"
    if score >= 3:
        return "状态不错，保持当前节奏即可"
    if score >= 2.5:
        return "状态一般，建议放慢节奏、穿插休息"
    return "状态偏低，建议减轻今日任务或暂停半天"


def compute_mood(db: Session, user: User, today: date) -> dict | None:
    """情绪综合评分 = 0.4×情绪项 + 0.3×完成项 + 0.2×压力项 + 0.1×达标项；今天没记录返回 None"""
    record = (
        db.query(MoodRecord)
        .filter(MoodRecord.user_id == user.id, MoodRecord.record_date == today)
        .first()
    )
    if record is None:
        return None

    emotion_item = 5 * (record.mood_score - 1) / 4
    completion_item = 5 * _today_completion_rate(db, user.id, today)
    pressure_item = 5 - compute_pressure(db, user.id)["score"] / 20
    streak_item = 5 * min(_streak_days(db, user.id, today), 7) / 7

    composite = round(
        0.4 * emotion_item + 0.3 * completion_item + 0.2 * pressure_item + 0.1 * streak_item,
        2,
    )
    return {
        "record_date": today,
        "mood_score": record.mood_score,
        "emotion_item": round(emotion_item, 2),
        "completion_item": round(completion_item, 2),
        "pressure_item": round(pressure_item, 2),
        "streak_item": round(streak_item, 2),
        "composite_score": composite,
        "suggestion": _mood_suggestion(composite),
        "need_relief": composite < 2.5,
    }


@router.post("/mood", response_model=MoodResult, summary="提交今日情绪自评（1~5）")
def submit_mood(
    payload: MoodSubmit,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    today = date.today()
    record = (
        db.query(MoodRecord)
        .filter(MoodRecord.user_id == user.id, MoodRecord.record_date == today)
        .first()
    )
    if record is None:
        record = MoodRecord(
            user_id=user.id, record_date=today, mood_score=payload.mood_score, note=payload.note
        )
        db.add(record)
    else:
        record.mood_score = payload.mood_score
        record.note = payload.note
    db.commit()
    return compute_mood(db, user, today)


@router.get("/mood/today", response_model=MoodResult | None, summary="查询今日情绪评分（未记录返回 null）")
def today_mood(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return compute_mood(db, user, date.today())


def _latest_analysis(db: Session, user_id: int, exam_id: int) -> Analysis | None:
    """该用户该科目最新一次 AI 分析"""
    return (
        db.query(Analysis)
        .filter(Analysis.user_id == user_id, Analysis.exam_id == exam_id)
        .order_by(Analysis.id.desc())
        .first()
    )


def _pick_exam(db: Session, user_id: int, exam_id: int | None, today: date) -> Exam | None:
    """指定考试优先；否则取最近一场未开考的考试"""
    query = db.query(Exam).filter(Exam.user_id == user_id, Exam.exam_date >= today)
    if exam_id:
        return query.filter(Exam.id == exam_id).first()
    return query.order_by(Exam.exam_date).first()


def compute_emergency(db: Session, user: User, exam_id: int | None = None) -> dict | None:
    """临时救急模式：为最近一场考试（或指定考试）生成高频基础考点冲刺清单"""
    today = date.today()
    exam = _pick_exam(db, user.id, exam_id, today)
    if exam is None:
        return None

    base = {
        "exam_id": exam.id,
        "subject": exam.subject,
        "exam_date": exam.exam_date,
        "days_left": (exam.exam_date - today).days,
        "items": [],
        "note": "",
    }
    analysis = _latest_analysis(db, user.id, exam.id)
    if analysis is None:
        base["note"] = "该科目还没有 AI 分析结果，先去「AI 复习分析」生成后才有冲刺清单"
        return base

    try:
        result = json.loads(analysis.result_json)
    except json.JSONDecodeError:
        base["note"] = "分析结果解析失败"
        return base

    items: list[dict] = []
    # 必考/常考考点，must 排在 common 前
    for f in sorted(result.get("exam_focus", []), key=lambda x: 0 if x.get("level") == "must" else 1):
        items.append({
            "content": f.get("content", ""),
            "kind": "考点",
            "level": f.get("level", ""),
            "weight": None,
            "source": f.get("source", ""),
            "basis": f.get("basis", ""),
        })
    # 高权重知识点，按权重从高到低
    for k in sorted(result.get("knowledge_points", []), key=lambda x: x.get("weight", 0), reverse=True):
        items.append({
            "content": k.get("name", ""),
            "kind": "知识点",
            "level": k.get("importance", ""),
            "weight": k.get("weight", 0),
            "source": k.get("source", ""),
            "basis": k.get("recommend_reason", ""),
        })
    base["items"] = items
    if not items:
        base["note"] = "该科目分析里没有可提取的考点"
    return base


@router.get("/emergency", response_model=EmergencyOut | None, summary="临时救急模式：考前冲刺清单")
def emergency(
    exam_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return compute_emergency(db, user, exam_id)


def compute_review(db: Session, user: User, exam_id: int | None = None) -> dict | None:
    """考前重点回顾列表：按权重从高到低列出该科目的必看知识点（考前几天通览用）"""
    today = date.today()
    exam = _pick_exam(db, user.id, exam_id, today)
    if exam is None:
        return None

    base = {
        "exam_id": exam.id,
        "subject": exam.subject,
        "exam_date": exam.exam_date,
        "days_left": (exam.exam_date - today).days,
        "items": [],
        "note": "",
    }
    analysis = _latest_analysis(db, user.id, exam.id)
    if analysis is None:
        base["note"] = "该科目还没有 AI 分析结果，先去「AI 复习分析」生成后才有重点回顾清单"
        return base

    try:
        result = json.loads(analysis.result_json)
    except json.JSONDecodeError:
        base["note"] = "分析结果解析失败"
        return base

    base["items"] = [
        {
            "name": k.get("name", ""),
            "weight": k.get("weight", 0),
            "importance": k.get("importance", "medium"),
            "suggest_hours": k.get("suggest_hours", 0),
            "suggest_minutes": k.get("suggest_minutes"),
            "source": k.get("source", ""),
            "basis": k.get("recommend_reason", ""),
        }
        for k in sorted(
            result.get("knowledge_points", []),
            key=lambda x: x.get("weight", 0),
            reverse=True,
        )
    ]
    if not base["items"]:
        base["note"] = "该科目分析里没有可回顾的知识点"
    return base


@router.get("/review", response_model=ReviewOut | None, summary="考前重点回顾列表：按权重列出必看清单")
def review(
    exam_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return compute_review(db, user, exam_id)


# 任务优先级 → 权重（1 高 / 2 中 / 3 低）
_PRIORITY_WEIGHT = {1: 1.0, 2: 0.6, 3: 0.3}


def compute_top3(db: Session, user: User) -> dict:
    """今日最重要的三件事：在今日（含逾期）未完成任务中按 权重+截止紧迫度+压力指数 打分取前三

    打分 = 40×优先级权重 + 35×截止紧迫度 + 25×(压力指数/100)；
    截止紧迫度：任务已逾期或考试当天取 1，否则 min(1, 7÷距考试天数)，无考试取 0。
    """
    today = date.today()
    score_pressure = compute_pressure(db, user.id)["score"]
    exams = {e.id: e for e in db.query(Exam).filter(Exam.user_id == user.id).all()}
    tasks = (
        db.query(Task)
        .filter(Task.user_id == user.id, Task.is_done.is_(False), Task.plan_date <= today)
        .all()
    )

    ranked = []
    for t in tasks:
        exam = exams.get(t.exam_id)
        days_left = (exam.exam_date - today).days if exam else None
        if t.plan_date < today or (days_left is not None and days_left <= 0):
            urgency = 1.0
        elif days_left is None:
            urgency = 0.0
        else:
            urgency = min(1.0, 7 / days_left)

        weight = _PRIORITY_WEIGHT.get(t.priority, 0.3)
        score = round(40 * weight + 35 * urgency + 25 * (score_pressure / 100), 1)

        bits = []
        if t.priority == 1:
            bits.append("优先级高")
        if t.plan_date < today:
            bits.append("已逾期")
        elif days_left is not None:
            bits.append(f"距{exam.subject}考试 {days_left} 天")

        ranked.append((score, {
            "task_id": t.id,
            "title": t.title,
            "subject": exam.subject if exam else "",
            "plan_date": t.plan_date,
            "priority": t.priority,
            "estimated_minutes": t.estimated_minutes,
            "score": score,
            "reason": " · ".join(bits) if bits else "按当前压力排序",
        }))

    ranked.sort(key=lambda x: x[0], reverse=True)
    top = [item for _, item in ranked[:3]]
    note = "" if top else "今天没有待完成任务，去「生成复习计划」安排一下吧"
    return {"items": top, "pressure": score_pressure, "note": note}


@router.get("/top3", response_model=Top3Out, summary="今日最重要的三件事（按权重+截止+压力置顶）")
def top3(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return compute_top3(db, user)


# 学习时段推荐只读统计，不写回任务。
@router.get("/timeslots", response_model=TimeSlotOut, summary="基于近28天专注习惯推荐学习时段")
def timeslots(exam_id: int | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from ..services.timeslots import recommend
    if exam_id is not None and not db.query(Exam).filter(Exam.id == exam_id, Exam.user_id == user.id).first():
        raise HTTPException(status_code=404, detail="考试不存在")
    return recommend(db, user.id, exam_id)


def compute_relief(db: Session, user: User, option: str) -> dict:
    """低情绪减负：把今日（含逾期）未完成任务在约束下重排到后续日期

    约束：① 不晚于该任务所属考试的日期；② 每日不超过全科共享的每日可用时长
    （暂停半天时今日容量取 0，减轻当日取一半）；③ 按任务优先级从高到低优先安排。
    排不下的任务进 conflicts 明确提示取舍，不硬塞到后续日期。
    """
    if option not in ("lighten", "halfday"):
        raise HTTPException(422, "不支持的减负选项")
    today = date.today()

    from ..services.study_planner import daily_budget
    daily_minutes = daily_budget(db, user.id)
    today_cap = 0 if option == "halfday" else daily_minutes // 2

    all_tasks = db.query(Task).filter(Task.user_id == user.id).all()
    tasks = [t for t in all_tasks if not t.is_done]
    exams = {e.id: e for e in db.query(Exam).filter(Exam.user_id == user.id).all()}

    movable = [t for t in tasks if t.plan_date <= today and t.start_time is None]
    frozen = [t for t in tasks if t.plan_date > today or t.start_time is not None]

    # 未来各天已被未完成任务占用的分钟数
    load: dict[date, int] = {}
    for t in frozen:
        load[t.plan_date] = load.get(t.plan_date, 0) + t.estimated_minutes
    for t in all_tasks:
        if t.is_done and t.plan_date >= today:
            load[t.plan_date] = load.get(t.plan_date, 0) + t.estimated_minutes

    def sort_key(t: Task):
        exam = exams.get(t.exam_id)
        return (t.priority, exam.exam_date if exam else date.max, t.plan_date)

    movable.sort(key=sort_key)

    moves, conflicts = [], []
    for task in frozen:
        if task.start_time is not None and task.plan_date < today:
            conflicts.append({'task_id': task.id, 'title': task.title, 'reason': '固定时段已过，请先手动改期或打卡'})
    if any(t.start_time is not None and t.plan_date == today for t in frozen) and load.get(today, 0) > today_cap:
        conflicts.append({'task_id': 0, 'title': '今日固定安排', 'reason': '固定时段与已完成任务已超过减负后的今日容量，请先调整固定时段'})
    for t in movable:
        exam = exams.get(t.exam_id)
        deadline = exam.exam_date if exam else today + timedelta(days=365)
        placed = None
        d = today
        while d <= deadline:
            if d == today and today_cap == 0:
                d += timedelta(days=1)
                continue
            cap = today_cap if d == today else daily_minutes
            used = load.get(d, 0)
            if used + t.estimated_minutes <= cap:
                placed = d
                break
            d += timedelta(days=1)

        if placed is None:
            conflicts.append({
                "task_id": t.id,
                "title": t.title,
                "reason": (
                    f"考前时间不足，无法在 {deadline.isoformat()} 前安排"
                    if deadline
                    else "每日可用时间不足，无法安排"
                ),
            })
            continue

        load[placed] = load.get(placed, 0) + t.estimated_minutes
        if placed != t.plan_date:
            moves.append({
                "task_id": t.id,
                "title": t.title,
                "from_date": t.plan_date,
                "to_date": placed,
                "minutes": t.estimated_minutes,
            })

    if conflicts:
        summary = f"将后移 {len(moves)} 个任务，另有 {len(conflicts)} 个任务考前排不下，需要取舍"
    elif moves:
        summary = f"将后移 {len(moves)} 个任务，今日负担相应减轻"
    else:
        summary = "当前安排已满足约束，无需调整"

    return {
        "option": option,
        "daily_hours": daily_minutes / 60,
        "today_capacity": today_cap,
        "moves": moves,
        "conflicts": conflicts,
        "summary": summary,
    }


@router.get("/relief", response_model=ReliefPlan, summary="低情绪减负：重排方案预览（未生效）")
def relief(
    option: str = "lighten",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return compute_relief(db, user, option)


@router.post("/relief/apply", response_model=ReliefPlan, summary="确认减负：按预览方案重排并生效")
def relief_apply(
    payload: ReliefApply,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plan = compute_relief(db, user, payload.option)
    if plan['conflicts']:
        raise HTTPException(409, "仍有任务无法安排，请先调整任务或每日时间")
    moves = {m["task_id"]: m["to_date"] for m in plan["moves"]}
    if moves:
        for t in (
            db.query(Task)
            .filter(Task.user_id == user.id, Task.id.in_(list(moves.keys())))
            .all()
        ):
            t.plan_date = moves[t.id]
        db.commit()
    return plan
