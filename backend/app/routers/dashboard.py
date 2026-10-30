"""首页聚合与统计接口"""
import json
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models.models import Analysis, Exam, FocusSession, Task, User
from ..schemas.schemas import (
    DailyStat,
    DashboardOut,
    DayStat,
    ExamDashboard,
    StatsOut,
    StatsOverviewOut,
    SubjectStat,
    WeeklyDayOut,
    WeeklyReportOut,
    WeeklyReportRequest,
    WeeklySubjectOut,
)
from ..services import prompts
from ..services.focus_history import archived_subjects
from ..services.llm_client import LLMError, chat_json
from ..utils.security import get_current_user

router = APIRouter()


def _days_left(exam_date: date) -> int:
    return max((exam_date - date.today()).days, 0)


WEEKLY_LEVELS = ("优秀", "良好", "一般", "薄弱")


def _mastery_level(score: int) -> str:
    if score >= 85:
        return "优秀"
    if score >= 70:
        return "良好"
    if score >= 55:
        return "一般"
    return "薄弱"


def _str_list(value, limit: int = 5) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(x).strip() for x in value if str(x).strip()][:limit]


@router.get("/dashboard", response_model=DashboardOut, summary="首页聚合：倒计时 + 今日待办 + 总进度")
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    exams = (
        db.query(Exam).filter(Exam.user_id == user.id).order_by(Exam.exam_date).all()
    )
    today_tasks = (
        db.query(Task)
        .filter(Task.user_id == user.id, Task.plan_date == date.today())
        .order_by(Task.is_done, Task.priority, Task.sort_order, Task.id)
        .all()
    )

    # 各科任务完成情况
    totals = dict(
        db.query(Task.exam_id, func.count(Task.id))
        .filter(Task.user_id == user.id)
        .group_by(Task.exam_id)
        .all()
    )
    dones = dict(
        db.query(Task.exam_id, func.count(Task.id))
        .filter(Task.user_id == user.id, Task.is_done.is_(True))
        .group_by(Task.exam_id)
        .all()
    )

    exam_list = []
    for exam in exams:
        total = totals.get(exam.id, 0)
        done = dones.get(exam.id, 0)
        exam_list.append(
            ExamDashboard(
                id=exam.id,
                subject=exam.subject,
                exam_date=exam.exam_date,
                days_left=_days_left(exam.exam_date),
                location=exam.location,
                duration_minutes=exam.duration_minutes,
                total_tasks=total,
                done_tasks=done,
                progress=round(done / total, 3) if total else 0.0,
            )
        )

    total_all = sum(totals.values())
    done_all = sum(dones.values())
    overall = {
        "total": total_all,
        "done": done_all,
        "rate": round(done_all / total_all, 3) if total_all else 0.0,
    }
    return DashboardOut(exams=exam_list, today_tasks=today_tasks, overall=overall)


@router.post(
    "/reports/weekly",
    response_model=WeeklyReportOut,
    summary="备考周报：近 7 天学习统计 + 大模型各科掌握度评测（FMZH-SRS-5.3.0）",
)
def weekly_report(
    payload: WeeklyReportRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 周报窗口：默认最近 7 天（含今天）；指定起始日时最多到第 7 天，且不统计未来
    today = date.today()
    week_start = payload.week_start if payload else None
    if week_start is None:
        end = today
        start = end - timedelta(days=6)
    else:
        start = week_start
        if start > today:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能生成未来日期的周报")
        end = min(start + timedelta(days=6), today)

    start_dt = datetime.combine(start, time.min)
    end_dt = datetime.combine(end + timedelta(days=1), time.min)

    # 番茄钟时长（口径同 /stats/overview：半开区间只比 start_time）
    sessions = (
        db.query(FocusSession)
        .filter(
            FocusSession.user_id == user.id,
            FocusSession.start_time >= start_dt,
            FocusSession.start_time < end_dt,
        )
        .all()
    )
    minutes_by_exam: dict[int | None, int] = {}
    minutes_by_day: dict[str, int] = {}
    for s in sessions:
        minutes_by_exam[s.exam_id] = minutes_by_exam.get(s.exam_id, 0) + s.duration_minutes
        key = s.start_time.date().isoformat()
        minutes_by_day[key] = minutes_by_day.get(key, 0) + s.duration_minutes

    # 窗口内任务：只统计本区间计划的任务，完成率不会因为未来的任务被拉低
    tasks = (
        db.query(Task)
        .filter(
            Task.user_id == user.id,
            Task.plan_date >= start,
            Task.plan_date <= end,
        )
        .all()
    )
    totals_by_exam: dict[int, int] = {}
    dones_by_exam: dict[int, int] = {}
    total_by_day: dict[str, int] = {}
    done_by_day: dict[str, int] = {}
    for t in tasks:
        key = t.plan_date.isoformat()
        totals_by_exam[t.exam_id] = totals_by_exam.get(t.exam_id, 0) + 1
        total_by_day[key] = total_by_day.get(key, 0) + 1
        if t.is_done:
            dones_by_exam[t.exam_id] = dones_by_exam.get(t.exam_id, 0) + 1
            done_by_day[key] = done_by_day.get(key, 0) + 1

    total_tasks = len(tasks)
    done_tasks = sum(dones_by_exam.values())
    rate = round(done_tasks / total_tasks, 3) if total_tasks else 0.0
    total_minutes = sum(minutes_by_exam.values())

    # 科目 = 有专注记录 ∪ 有任务的科目
    exams = {e.id: e for e in db.query(Exam).filter(Exam.user_id == user.id).all()}
    exam_ids = {eid for eid in minutes_by_exam if eid is not None} | set(totals_by_exam)
    subjects: list[WeeklySubjectOut] = []
    for eid in exam_ids:
        exam = exams.get(eid)
        if exam is None:
            continue
        total = totals_by_exam.get(eid, 0)
        done = dones_by_exam.get(eid, 0)
        subjects.append(
            WeeklySubjectOut(
                exam_id=eid,
                subject=exam.subject,
                minutes=minutes_by_exam.get(eid, 0),
                total_tasks=total,
                done_tasks=done,
                rate=round(done / total, 3) if total else 0.0,
                exam_date=exam.exam_date,
                days_left=_days_left(exam.exam_date),
            )
        )
    subjects.extend(WeeklySubjectOut(**item) for item in archived_subjects(sessions))
    free_minutes = sum(s.duration_minutes for s in sessions if s.exam_id is None and not s.subject_snapshot)
    if free_minutes:
        subjects.append(
            WeeklySubjectOut(
                exam_id=None,
                subject="未指定科目",
                minutes=free_minutes,
                total_tasks=0,
                done_tasks=0,
                rate=0.0,
            )
        )
    subjects.sort(key=lambda s: (s.minutes, s.rate), reverse=True)

    # 大模型评测只针对真实科目；未指定科目的自由专注不评分
    metrics = [
        {
            "subject": s.subject,
            "minutes": s.minutes,
            "total_tasks": s.total_tasks,
            "done_tasks": s.done_tasks,
            "rate": s.rate,
            "days_left": s.days_left,
        }
        for s in subjects
        if s.exam_id is not None
    ]
    ai: dict = {}
    if metrics:
        try:
            if settings.LLM_MOCK:
                ai = prompts.mock_generate_weekly_report(metrics)
            else:
                ai = chat_json(
                    prompts.WEEKLY_REPORT_SYSTEM_PROMPT,
                    prompts.build_weekly_report_user_prompt(start.isoformat(), end.isoformat(), metrics),
                    max_tokens=2000,
                )
        except LLMError as e:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    ai = ai if isinstance(ai, dict) else {}

    by_subject = {}
    for item in (ai.get('subjects') if isinstance(ai.get('subjects'),list) else []):
        if isinstance(item, dict):
            name = str(item.get("subject") or "").strip()
            if name:
                by_subject[name] = item

    # 合并评测：大模型缺项/非法值时用启发式评分兜底，保证每科都有结果
    for s in subjects:
        if s.exam_id is None:
            continue
        fallback = prompts.mock_subject_evaluation(
            {
                "subject": s.subject,
                "minutes": s.minutes,
                "total_tasks": s.total_tasks,
                "done_tasks": s.done_tasks,
                "rate": s.rate,
                "days_left": s.days_left,
            }
        )
        item = by_subject.get(s.subject) or {}
        try:
            mastery = int(item.get("mastery"))
        except (TypeError, ValueError):
            mastery = fallback["mastery"]
        mastery = max(0, min(100, mastery))
        s.mastery = mastery
        s.level = item.get("level") if item.get("level") in WEEKLY_LEVELS else _mastery_level(mastery)
        s.comment = str(item.get("comment") or "").strip() or fallback["comment"]
        s.suggestions = _str_list(item.get("suggestions")) or fallback["suggestions"]

    scored = [s.mastery for s in subjects if s.exam_id is not None and s.mastery is not None]
    overall_mastery = None
    try:
        overall_mastery = int(ai.get("overall_mastery"))
    except (TypeError, ValueError):
        pass
    if overall_mastery is None and scored:
        overall_mastery = int(round(sum(scored) / len(scored)))
    if overall_mastery is not None:
        overall_mastery = max(0, min(100, overall_mastery))

    summary = str(ai.get("summary") or "").strip()
    if not summary:
        summary = (
            f"本周共学习 {total_minutes} 分钟，完成任务 {done_tasks}/{total_tasks}"
            f"（完成率 {rate:.0%}）。"
            if metrics
            else "本周还没有学习记录，先去完成一些任务或用番茄钟专注一次吧。"
        )

    highlights = _str_list(ai.get("highlights"))
    if not highlights and metrics:
        top = max((s for s in subjects if s.exam_id is not None), key=lambda s: s.minutes, default=None)
        if top:
            highlights = [f"本周学习时长最高：{top.subject}（{top.minutes} 分钟）"]
    advice = _str_list(ai.get("next_week_advice"))
    if not advice and metrics:
        advice = ["保持每天至少 1 个番茄钟的节奏。", "考前留出整卷自测时间，及时清理错题。"]

    note = ""
    if not subjects:
        note = "该区间还没有学习记录，完成一些任务或用番茄钟专注一次后再生成周报。"
    elif not metrics:
        note = "该区间只有自由专注或已删除考试的历史时长，保留分钟数，不生成当前科目掌握度评测。"

    # 每日序列：窗口内每天补一条，保证报表连续
    daily: list[WeeklyDayOut] = []
    cur = start
    while cur <= end:
        key = cur.isoformat()
        total = total_by_day.get(key, 0)
        done = done_by_day.get(key, 0)
        daily.append(
            WeeklyDayOut(
                date=key,
                minutes=minutes_by_day.get(key, 0),
                total=total,
                done=done,
                rate=round(done / total, 3) if total else 0.0,
            )
        )
        cur += timedelta(days=1)

    return WeeklyReportOut(
        week_start=start.isoformat(),
        week_end=end.isoformat(),
        generated_at=datetime.now(),
        total_minutes=total_minutes,
        total_tasks=total_tasks,
        done_tasks=done_tasks,
        rate=rate,
        active_days=sum(1 for d in daily if d.minutes > 0),
        overall_mastery=overall_mastery,
        summary=summary,
        highlights=highlights,
        next_week_advice=advice,
        subjects=subjects,
        days=daily,
        note=note,
    )


# ⚠ 必须声明在 /stats/{exam_id} 之前：FastAPI 按注册顺序匹配，
# 否则 /stats/overview 会先被 {exam_id:int} 捕获、"overview" 当整数解析 -> 422。
@router.get(
    "/stats/overview",
    response_model=StatsOverviewOut,
    summary="学习统计总览：各科学习时长 + 完成率 + 每日趋势（FMZH-SRS-5.2.0）",
)
def stats_overview(
    days: int = 7,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    days = max(1, min(days, 90))
    end = date.today()
    start = end - timedelta(days=days - 1)
    start_dt = datetime.combine(start, time.min)
    end_dt = datetime.combine(end + timedelta(days=1), time.min)

    # 番茄钟：窗口内一次取回，Python 侧按科目 / 按天累加（口径同 focus.py，半开区间只比 start_time）
    sessions = (
        db.query(FocusSession)
        .filter(
            FocusSession.user_id == user.id,
            FocusSession.start_time >= start_dt,
            FocusSession.start_time < end_dt,
        )
        .all()
    )
    minutes_by_exam: dict[int | None, int] = {}
    minutes_by_day: dict[str, int] = {}
    for s in sessions:
        minutes_by_exam[s.exam_id] = minutes_by_exam.get(s.exam_id, 0) + s.duration_minutes
        key = s.start_time.date().isoformat()
        minutes_by_day[key] = minutes_by_day.get(key, 0) + s.duration_minutes

    # 任务：全量课程进度（与首页 /dashboard 口径一致）
    totals = dict(
        db.query(Task.exam_id, func.count(Task.id))
        .filter(Task.user_id == user.id)
        .group_by(Task.exam_id)
        .all()
    )
    dones = dict(
        db.query(Task.exam_id, func.count(Task.id))
        .filter(Task.user_id == user.id, Task.is_done.is_(True))
        .group_by(Task.exam_id)
        .all()
    )

    # 历史报表：窗口内按计划日期聚合任务
    window_tasks = (
        db.query(Task)
        .filter(
            Task.user_id == user.id,
            Task.plan_date >= start,
            Task.plan_date <= end,
        )
        .all()
    )
    total_by_day: dict[str, int] = {}
    done_by_day: dict[str, int] = {}
    for t in window_tasks:
        key = t.plan_date.isoformat()
        total_by_day[key] = total_by_day.get(key, 0) + 1
        if t.is_done:
            done_by_day[key] = done_by_day.get(key, 0) + 1

    # 按科目汇总：番茄钟涉及的科目 ∪ 有任务的科目
    exams = {e.id: e for e in db.query(Exam).filter(Exam.user_id == user.id).all()}
    exam_ids = {eid for eid in minutes_by_exam if eid is not None} | set(totals)
    subjects: list[SubjectStat] = []
    for eid in exam_ids:
        exam = exams.get(eid)
        if exam is None:
            continue
        total = totals.get(eid, 0)
        done = dones.get(eid, 0)
        subjects.append(
            SubjectStat(
                exam_id=eid,
                subject=exam.subject,
                minutes=minutes_by_exam.get(eid, 0),
                total_tasks=total,
                done_tasks=done,
                rate=round(done / total, 3) if total else 0.0,
                exam_date=exam.exam_date,
                days_left=_days_left(exam.exam_date),
            )
        )
    subjects.extend(SubjectStat(**item) for item in archived_subjects(sessions))
    free_minutes = sum(s.duration_minutes for s in sessions if s.exam_id is None and not s.subject_snapshot)
    if free_minutes:
        subjects.append(
            SubjectStat(
                exam_id=None,
                subject="未指定科目",
                minutes=free_minutes,
                total_tasks=0,
                done_tasks=0,
                rate=0.0,
            )
        )
    subjects.sort(key=lambda s: (s.minutes, s.rate), reverse=True)

    # 每日序列：窗口内每天补一条，无记录补 0，保证图表 x 轴连续
    daily: list[DayStat] = []
    cur = start
    while cur <= end:
        key = cur.isoformat()
        total = total_by_day.get(key, 0)
        done = done_by_day.get(key, 0)
        daily.append(
            DayStat(
                date=key,
                minutes=minutes_by_day.get(key, 0),
                total=total,
                done=done,
                rate=round(done / total, 3) if total else 0.0,
            )
        )
        cur += timedelta(days=1)

    total_all = sum(totals.values())
    done_all = sum(dones.values())
    return StatsOverviewOut(
        range_days=days,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        total_minutes=sum(minutes_by_exam.values()),
        total_tasks=total_all,
        done_tasks=done_all,
        rate=round(done_all / total_all, 3) if total_all else 0.0,
        subjects=subjects,
        days=daily,
    )


@router.get("/stats/{exam_id}", response_model=StatsOut, summary="单科统计：完成率 + 每日情况 + 知识点权重")
def exam_stats(
    exam_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exam = db.query(Exam).filter(Exam.id == exam_id, Exam.user_id == user.id).first()
    if exam is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="考试不存在")

    tasks = (
        db.query(Task)
        .filter(Task.user_id == user.id, Task.exam_id == exam_id)
        .order_by(Task.plan_date)
        .all()
    )
    total = len(tasks)
    done = sum(1 for t in tasks if t.is_done)

    # 按日期聚合
    by_date: dict[str, DailyStat] = {}
    for t in tasks:
        key = t.plan_date.isoformat()
        stat = by_date.setdefault(key, DailyStat(date=key, total=0, done=0))
        stat.total += 1
        if t.is_done:
            stat.done += 1

    # 最新一次分析的知识点权重
    analysis = (
        db.query(Analysis)
        .filter(Analysis.user_id == user.id, Analysis.exam_id == exam_id)
        .order_by(Analysis.id.desc())
        .first()
    )
    knowledge_points = []
    if analysis:
        try:
            result = json.loads(analysis.result_json)
            knowledge_points = [
                {"name": kp.get("name", ""), "weight": kp.get("weight", 0)}
                for kp in result.get("knowledge_points", [])
            ]
        except json.JSONDecodeError:
            pass

    return StatsOut(
        exam_id=exam_id,
        subject=exam.subject,
        days_left=_days_left(exam.exam_date),
        total_tasks=total,
        done_tasks=done,
        rate=round(done / total, 3) if total else 0.0,
        by_date=list(by_date.values()),
        knowledge_points=knowledge_points,
    )
