"""特色功能接口（模块7）：压力指数 / 情绪记录 / 救急模式等
公式口径见 README 第 3.3、3.4 节，实现照抄，不要自行改动。
"""
from ..services.pressure import beijing_day
import json
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.models import Analysis, Exam, MoodRecord, Task, User, UserProfile, Collection, Material, QuizAttempt
from ..schemas.schemas import (
    EmergencyOut,
    MoodResult,
    MoodSubmit,
    PressureOut,
    PressureHistoryOut,
    ReliefApply,
    ReliefPlan,
    ReviewOut,
    TimeSlotOut,
    Top3Out,
)
from ..utils.security import get_current_user
# 实时值与每日任务共用原公式；读取接口不触发写入。
from ..services.pressure import compute_pressure, current_pressure, history as pressure_history

router = APIRouter()


@router.get("/pressure", response_model=PressureOut, summary="实时压力及今日自动记录状态")
def pressure(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return current_pressure(db, user.id)


@router.get("/pressure/history", response_model=PressureHistoryOut, summary="当前账号实际每日压力记录")
def daily_pressure_history(days: int = Query(default=7, ge=1, le=31), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return pressure_history(db, user.id, days)


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
    pressure_value = compute_pressure(db, user.id, today)
    pressure_item = 5 - pressure_value.get('raw_score', pressure_value['score']) / 20
    streak_item = 5 * min(_streak_days(db, user.id, today), 7) / 7

    composite = 0.4 * emotion_item + 0.3 * completion_item + 0.2 * pressure_item + 0.1 * streak_item
    from ..services.mood_advice import advice
    previous = {row.record_date:row.composite_raw for row in db.query(MoodRecord).filter(
        MoodRecord.user_id == user.id, MoodRecord.record_date < today).order_by(MoodRecord.id).all()}
    return {
        "record_date": today,
        "mood_score": record.mood_score,
        "emotion_item": round(emotion_item, 2),
        "completion_item": round(completion_item, 2),
        "pressure_item": round(pressure_item, 2),
        "streak_item": round(streak_item, 2),
        "composite_score": round(composite,2),
        "raw_score": composite,
        **advice(composite,today,user.id,previous),
        "need_relief": composite < 2.5,
    }


@router.post("/mood", response_model=MoodResult, summary="提交今日情绪自评（1~5）")
def submit_mood(
    payload: MoodSubmit,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from ..services.task_conflicts import lock_schedule
    lock_schedule(db, user.id, auth_key=user.auth_key)
    today = beijing_day()
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
    db.flush()
    result = compute_mood(db, user, today)
    record.composite_raw = result['raw_score']
    db.commit()
    return result


@router.get("/mood/today", response_model=MoodResult | None, summary="查询今日情绪评分（未记录返回 null）")
def today_mood(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return compute_mood(db, user, beijing_day())


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
    today = beijing_day()
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
    today = beijing_day()
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
    try:
        result = json.loads(analysis.result_json) if analysis else {}
        if not isinstance(result, dict):
            result = {}
    except (ValueError, TypeError):
        result = {}

    base["items"] = [
        {
            "name": k.get("name", ""),
            "weight": k.get("weight", 0),
            "importance": k.get("importance", "medium"),
            "suggest_hours": k.get("suggest_hours", 0),
            "suggest_minutes": k.get("suggest_minutes"),
            "source": k.get("source", ""),
            "basis": k.get("recommend_reason", ""),
            "kind": "knowledge",
        }
        for k in sorted(
            result.get("knowledge_points", []),
            key=lambda x: x.get("weight", 0),
            reverse=True,
        )
    ]
    unassigned, notebook = [], []
    from ..services.mistakes import question_key

    question_map = {}
    material_map = {
        m.id: m for m in db.query(Material).filter(Material.user_id == user.id).all()
    }
    for item in (
        db.query(Collection)
        .filter(Collection.user_id == user.id)
        .order_by(Collection.id.desc())
        .all()
    ):
        if item.item_type == "material":
            material = material_map.get(item.material_id)
            if not material or material.exam_id != exam.id:
                continue
            notebook.append(
                dict(
                    name=item.title or material.title,
                    weight=0,
                    source="资料收藏",
                    kind="material",
                    basis=(
                        material.description
                        or material.text_content
                        or "打开资料库查看原文"
                    )[:1200],
                    material_id=material.id,
                    collection_id=item.id,
                )
            )
        else:
            question_map[item.question_key or question_key(item.title)] = item
            try:
                content = json.loads(item.content or "{}")
            except ValueError:
                content = {"note": item.content}
            if not isinstance(content, dict):
                content = {}
            scope = content.get("exam_id")
            entry = dict(
                name=item.title,
                weight=0,
                source="自测错题" if item.source == "quiz" else "手动题目收藏",
                kind="question",
                collection_id=item.id,
                basis="；".join(
                    str(content[k])
                    for k in ("knowledge_point", "answer", "analysis", "note")
                    if content.get(k)
                )[:1200],
            )
            if content.get("archived_subject"):
                entry["source"] = (
                    f"历史题目 · {content['archived_subject']}（考试已删除）"
                )
            if (
                scope == exam.id
                and item.created_at
                and exam.created_at
                and item.created_at < exam.created_at
            ):
                entry["source"] = "待重新归类"
                unassigned.append(entry)
            elif scope == exam.id:
                notebook.append(entry)
            elif scope is None:
                unassigned.append(entry)
    # 同一道题只在错题本留一份，仍可属于多个实际做过该题的科目。
    seen = {
        question_key(item["name"]) for item in notebook if item["kind"] == "question"
    }
    attempts = (
        db.query(QuizAttempt)
        .filter_by(user_id=user.id, exam_id=exam.id, status="submitted")
        .order_by(QuizAttempt.submitted_at.desc())
    )
    for attempt in attempts:
        try:
            payload = json.loads(attempt.result_json or "{}")
        except (ValueError, TypeError):
            continue
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            continue
        for item in payload["items"]:
            if (
                not isinstance(item, dict)
                or item.get("correct") is not False
                or not isinstance(item.get("question"), str)
            ):
                continue
            key = question_key(item["question"])
            collection = question_map.get(key)
            if collection is None or key in seen:
                continue
            seen.add(key)
            notebook.append(
                dict(
                    name=item["question"],
                    kind="question",
                    source="自测错题",
                    weight=0,
                    collection_id=collection.id,
                    basis="；".join(
                        str(item[k])
                        for k in ("knowledge_point", "answer", "analysis")
                        if item.get(k)
                    )[:1200],
                )
            )
    base["items"] = notebook + base["items"]
    assigned_questions = {
        item["collection_id"] for item in notebook if item["kind"] == "question"
    }
    base["unassigned"] = [
        item for item in unassigned if item["collection_id"] not in assigned_questions
    ]
    if not base["items"]:
        base["note"] = (
            "该科目暂无错题、收藏或分析知识点。未分类题目单独列出，不混入其他科目。"
        )
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

    打分 = (40+25×压力/100)×知识点权重 + 35×截止紧迫度 + 10×任务优先级权重；
    无知识点关联时明确用任务优先级作为权重，不伪造知识点依据。
    截止紧迫度：任务已逾期或考试当天取 1，否则 min(1, 7÷距考试天数)，无考试取 0。
    """
    today = beijing_day()
    current_pressure_value = compute_pressure(db, user.id)
    score_pressure = current_pressure_value.get(
        "raw_score", current_pressure_value["score"]
    )
    exams = {e.id: e for e in db.query(Exam).filter(Exam.user_id == user.id).all()}
    tasks = (
        db.query(Task)
        .filter(
            Task.user_id == user.id, Task.is_done.is_(False), Task.plan_date <= today
        )
        .all()
    )

    points_by_exam = {}
    for analysis in (
        db.query(Analysis)
        .filter(Analysis.user_id == user.id)
        .order_by(Analysis.id)
        .all()
    ):
        try:
            points_by_exam[analysis.exam_id] = json.loads(analysis.result_json).get(
                "knowledge_points", []
            )
        except (ValueError, AttributeError):
            continue
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

        points = points_by_exam.get(t.exam_id, [])
        linked = [
            p
            for p in points
            if isinstance(p, dict)
            and p.get("name")
            and (
                p["name"] == t.knowledge_point
                or (
                    not t.knowledge_point
                    and len(p["name"]) >= 2
                    and p["name"] in (t.title + " " + t.detail)
                )
            )
        ]
        weight = max(
            (float(p.get("weight", 0)) for p in linked),
            default=_PRIORITY_WEIGHT.get(t.priority, 0.3),
        )
        score = (
            (40 + 25 * score_pressure / 100) * weight
            + 35 * urgency
            + 10 * _PRIORITY_WEIGHT.get(t.priority, 0.3)
        )

        bits = []
        bits.append(
            "知识点权重：" + "、".join(p["name"] for p in linked)
            if linked
            else "未关联知识点，按任务优先级"
        )
        if t.priority == 1:
            bits.append("优先级高")
        if t.plan_date < today:
            bits.append("已逾期")
        elif days_left is not None:
            bits.append(f"距{exam.subject}考试 {days_left} 天")

        ranked.append(
            (
                score,
                {
                    "task_id": t.id,
                    "title": t.title,
                    "subject": exam.subject if exam else "",
                    "plan_date": t.plan_date,
                    "priority": t.priority,
                    "estimated_minutes": t.estimated_minutes,
                    "score": score,
                    "reason": " · ".join(bits) if bits else "按当前压力排序",
                },
            )
        )

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


@router.get("/relief", response_model=ReliefPlan, summary="低情绪减负：只读预览今日半天与跨科调整")
def relief(option: str = "lighten", half: str = "afternoon", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from ..services.relief import preview
    return preview(db, user.id, option, half)


@router.post("/relief/apply", response_model=ReliefPlan, summary="确认减负：锁内重验预览并原子调整")
def relief_apply(payload: ReliefApply, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from ..services.relief import apply
    return apply(db, user.id, payload)
