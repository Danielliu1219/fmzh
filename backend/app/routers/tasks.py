"""任务接口：今日待办 / 按条件查询 / 手动添加 / 编辑 / 冲突预检 / 打卡"""
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.models import Exam, Task, User
from ..schemas.schemas import (
    ConflictCheckOut,
    ConflictCheckRequest,
    TaskCreate,
    TaskOut,
    TaskUpdate,
)
from ..services.schedule_service import check_conflict
from ..utils.security import get_current_user

router = APIRouter()


def _get_own_task(db: Session, user: User, task_id: int) -> Task:
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == user.id).first()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    return task


@router.get("/today", response_model=list[TaskOut], summary="今日待办")
def today_tasks(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(Task)
        .filter(Task.user_id == user.id, Task.plan_date == date.today())
        .order_by(Task.is_done, Task.priority, Task.sort_order, Task.id)
        .all()
    )


@router.get("", response_model=list[TaskOut], summary="按日期/科目查询任务")
def list_tasks(
    plan_date: date | None = None,
    exam_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Task).filter(Task.user_id == user.id)
    if plan_date is not None:
        query = query.filter(Task.plan_date == plan_date)
    if exam_id is not None:
        query = query.filter(Task.exam_id == exam_id)
    return query.order_by(Task.plan_date, Task.is_done, Task.priority, Task.sort_order).all()


@router.post("", response_model=TaskOut, summary="手动添加任务")
def create_task(
    payload: TaskCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exam = (
        db.query(Exam).filter(Exam.id == payload.exam_id, Exam.user_id == user.id).first()
    )
    if exam is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="考试不存在")
    task = Task(user_id=user.id, source="manual", **payload.model_dump())
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.post("/check-conflict", response_model=ConflictCheckOut, summary="任务冲突检测（2.8：同一天总时长超上限提醒）")
def check_task_conflict(
    payload: ConflictCheckRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """保存前预检：当天已有任务总时长 + 新增时长超过上限时 conflict=true，前端弹提醒（不阻止保存）"""
    return check_conflict(
        db,
        user.id,
        payload.plan_date,
        payload.estimated_minutes,
        exclude_task_id=payload.exclude_task_id,
        daily_limit_minutes=payload.daily_limit_minutes,
    )


@router.put("/{task_id}", response_model=TaskOut, summary="编辑任务（2.6：修改名称/日期/时长/优先级/科目）")
def update_task(
    task_id: int,
    payload: TaskUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = _get_own_task(db, user, task_id)
    data = payload.model_dump(exclude_none=True)
    if "exam_id" in data:
        exam = (
            db.query(Exam)
            .filter(Exam.id == data["exam_id"], Exam.user_id == user.id)
            .first()
        )
        if exam is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="考试不存在")
    for field, value in data.items():
        setattr(task, field, value)
    db.commit()
    db.refresh(task)
    return task


@router.post("/{task_id}/checkin", response_model=TaskOut, summary="打卡完成")
def checkin(
    task_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = _get_own_task(db, user, task_id)
    if not task.is_done:
        task.is_done = True
        task.done_at = datetime.now()
        db.commit()
        db.refresh(task)
    return task


@router.delete("/{task_id}/checkin", response_model=TaskOut, summary="取消打卡")
def uncheckin(
    task_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = _get_own_task(db, user, task_id)
    task.is_done = False
    task.done_at = None
    db.commit()
    db.refresh(task)
    return task


@router.delete("/{task_id}", summary="删除任务")
def delete_task(
    task_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = _get_own_task(db, user, task_id)
    db.delete(task)
    db.commit()
    return {"ok": True}
