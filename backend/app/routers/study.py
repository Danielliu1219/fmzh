"""全科每日预算与可确认的跨科排程。"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.models import FocusGoal, StudySetting, User
from ..services import study_planner
from ..utils.security import get_current_user

router = APIRouter()


class BudgetIn(BaseModel):
    daily_minutes: int = Field(ge=30, le=960)


class ConfirmIn(BaseModel):
    fingerprint: str


@router.get('/settings')
def settings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {'daily_minutes': study_planner.daily_budget(db, user.id)}


@router.put('/settings')
def save_settings(payload: BudgetIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(StudySetting, user.id)
    if row is None:
        row = StudySetting(user_id=user.id)
        db.add(row)
    row.daily_minutes = payload.daily_minutes
    goal = db.query(FocusGoal).filter(FocusGoal.user_id == user.id, FocusGoal.goal_date == date.today()).first()
    if goal is None:
        goal = FocusGoal(user_id=user.id, goal_date=date.today())
        db.add(goal)
    goal.target_minutes = payload.daily_minutes
    db.commit()
    return {'daily_minutes': row.daily_minutes}


@router.get('/plan/preview')
def plan_preview(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return study_planner.preview(db, user.id)


@router.post('/plan/confirm')
def plan_confirm(payload: ConfirmIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan = study_planner.preview(db, user.id)
    if payload.fingerprint != plan['fingerprint']:
        raise HTTPException(409, '任务或预算已经变化，请重新预览')
    if plan['conflicts']:
        raise HTTPException(409, '有任务无法在考试前安排，请先调整预算或任务')
    study_planner.apply(db, user.id, plan)
    return {'ok': True}
