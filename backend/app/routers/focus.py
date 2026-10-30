"""番茄钟与每日学习目标（FMZH-SRS-2.10.0）

计时结束后记录一条专注记录，时长按科目归入学习统计；
学生可设定当日学习时长目标，系统统计达成情况。
"""
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.models import Exam, FocusGoal, FocusSession, User
from ..schemas.schemas import (
    FocusExamStat,
    FocusGoalOut,
    FocusGoalUpdate,
    FocusSessionCreate,
    FocusSessionOut,
    FocusTodayOut,
)
from ..utils.security import get_current_user
from ..services.study_planner import daily_budget
from ..services.timeslots import CHINA, local_time

router = APIRouter()


def _subject_map(db: Session, user: User, exam_ids: set[int]) -> dict[int, str]:
    """按考试 id 取科目名，用于响应中回填 subject"""
    if not exam_ids:
        return {}
    exams = (
        db.query(Exam.id, Exam.subject)
        .filter(Exam.user_id == user.id, Exam.id.in_(exam_ids))
        .all()
    )
    return {eid: name for eid, name in exams}


def _to_out(session: FocusSession, subject: str) -> FocusSessionOut:
    return FocusSessionOut(
        id=session.id,
        exam_id=session.exam_id,
        subject=subject or session.subject_snapshot,
        archived=session.exam_id is None and bool(session.subject_snapshot),
        duration_minutes=session.duration_minutes,
        start_time=session.start_time,
        end_time=session.end_time,
        created_at=session.created_at,
    )


def _day_range(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min)
    return start, start + timedelta(days=1)


@router.post("/sessions", response_model=FocusSessionOut, summary="记录一次番茄钟")
def create_session(
    payload: FocusSessionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.exam_id is not None:
        exam = (
            db.query(Exam)
            .filter(Exam.id == payload.exam_id, Exam.user_id == user.id)
            .first()
        )
        if exam is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="考试不存在")

    now = datetime.now(CHINA).replace(tzinfo=None)
    end_time = local_time(payload.end_time) if payload.end_time else now
    start_time = local_time(payload.start_time) if payload.start_time else (end_time - timedelta(minutes=payload.duration_minutes))
    if (end_time <= start_time or end_time > now + timedelta(seconds=5)
            or abs((end_time-start_time).total_seconds()/60-payload.duration_minutes) > 1):
        raise HTTPException(status_code=422, detail="专注起止需与记录分钟一致，且不能晚于当前时间")

    session = FocusSession(
        user_id=user.id,
        exam_id=payload.exam_id,
        subject_snapshot=exam.subject if payload.exam_id is not None else "",
        start_time=start_time,
        end_time=end_time,
        duration_minutes=payload.duration_minutes,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    subject = _subject_map(db, user, {payload.exam_id}).get(payload.exam_id, "")
    return _to_out(session, subject)


@router.get("/today", response_model=FocusTodayOut, summary="今日专注汇总与目标达成")
def today_summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = date.today()
    start, end = _day_range(today)
    sessions = (
        db.query(FocusSession)
        .filter(
            FocusSession.user_id == user.id,
            FocusSession.start_time >= start,
            FocusSession.start_time < end,
        )
        .order_by(FocusSession.start_time)
        .all()
    )

    goal = (
        db.query(FocusGoal)
        .filter(FocusGoal.user_id == user.id, FocusGoal.goal_date == today)
        .first()
    )
    goal_minutes = goal.target_minutes if goal else daily_budget(db, user.id)

    # 按科目聚合
    minutes_by_exam = {}
    for s in sessions:
        key = (s.exam_id, s.subject_snapshot if s.exam_id is None else "")
        minutes_by_exam[key] = minutes_by_exam.get(key, 0) + s.duration_minutes

    subjects = _subject_map(db, user, {eid for eid, _ in minutes_by_exam if eid is not None})
    by_exam = [
        FocusExamStat(
            exam_id=eid,
            subject=subjects.get(eid, "") if eid is not None else (f"{snapshot}（已删除考试）" if snapshot else "未指定科目"),
            archived=eid is None and bool(snapshot),
            minutes=minutes,
        )
        for (eid, snapshot), minutes in minutes_by_exam.items()
    ]

    total_minutes = sum(minutes_by_exam.values())
    return FocusTodayOut(
        date=today.isoformat(),
        total_minutes=total_minutes,
        goal_minutes=goal_minutes,
        achieved=goal_minutes > 0 and total_minutes >= goal_minutes,
        session_count=len(sessions),
        by_exam=by_exam,
    )


@router.put("/goal", response_model=FocusGoalOut, summary="设定当日学习时长目标")
def set_goal(
    payload: FocusGoalUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    goal_date = payload.goal_date or date.today()
    goal = (
        db.query(FocusGoal)
        .filter(FocusGoal.user_id == user.id, FocusGoal.goal_date == goal_date)
        .first()
    )
    if goal is None:
        goal = FocusGoal(user_id=user.id, goal_date=goal_date, target_minutes=payload.target_minutes)
        db.add(goal)
    else:
        goal.target_minutes = payload.target_minutes
    db.commit()
    db.refresh(goal)
    return FocusGoalOut(goal_date=goal.goal_date, target_minutes=goal.target_minutes)


@router.get("/sessions", response_model=list[FocusSessionOut], summary="番茄钟记录（按日期/科目查询）")
def list_sessions(
    day: date | None = None,
    exam_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(FocusSession).filter(FocusSession.user_id == user.id)
    if day is not None:
        start, end = _day_range(day)
        query = query.filter(FocusSession.start_time >= start, FocusSession.start_time < end)
    if exam_id is not None:
        query = query.filter(FocusSession.exam_id == exam_id)
    sessions = query.order_by(FocusSession.start_time.desc()).all()

    subjects = _subject_map(db, user, {s.exam_id for s in sessions if s.exam_id is not None})
    return [_to_out(s, subjects.get(s.exam_id, "") if s.exam_id is not None else "") for s in sessions]
