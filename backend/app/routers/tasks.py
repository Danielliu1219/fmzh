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
    TaskCreateOut,
    TaskPreviewRequest,
    TaskPreviewOut,
    TaskMoveIn,
    TaskMovePreviewOut,
    TaskOut,
    TaskUpdate,
)
from ..services.schedule_service import check_conflict
from ..services import task_service, task_moves
from ..services.study_planner import daily_budget
from ..services.task_conflicts import detect_candidates, find_overlaps
from ..services.task_conflicts import lock_schedule
from ..services.task_details import timed_minutes
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


@router.post('/preview', response_model=TaskPreviewOut, summary='预览任务日期、重复次数及全科预算提醒（只读）')
def preview_task(payload: TaskPreviewRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return task_service.preview_tasks(db, user.id, payload)


@router.post("", response_model=TaskCreateOut, summary="手动添加任务或有限重复任务")
def create_task(
    payload: TaskCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return task_service.create_tasks(db, user.id, payload)


@router.post("/check-conflict", response_model=ConflictCheckOut, summary="任务固定时段重叠及全科日预算预检（2.8）")
def check_task_conflict(
    payload: ConflictCheckRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """只读预检：日预算和同日真实时段交集分别返回，最终写入还会重验时段。"""
    if payload.exclude_task_id:
        task_service.own_task(db, user.id, payload.exclude_task_id)
    if payload.exam_id is not None:
        task_service.own_exam(db, user.id, payload.exam_id)
    data = payload.model_dump()
    # 仅预检的旧请求无需科目；复用创建规则验证成对时段及实际分钟。
    try:
        duration = timed_minutes(payload.start_time, payload.end_time)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    limit = daily_budget(db, user.id)
    if payload.daily_limit_minutes is not None:
        limit = min(limit, payload.daily_limit_minutes)
    result = check_conflict(
        db,
        user.id,
        payload.plan_date,
        duration if duration is not None else payload.estimated_minutes,
        exclude_task_id=payload.exclude_task_id,
        daily_limit_minutes=limit,
    )
    overlaps = detect_candidates(db, user.id, [data], payload.exclude_task_id)
    return {**result, 'budget_exceeded': result['conflict'], 'overlaps': overlaps,
            'conflict': result['conflict'] or bool(overlaps)}


@router.get('/conflicts', summary='查看当前账号固定时段的重叠任务（只读）')
def list_conflicts(plan_date: date | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(Task).filter(Task.user_id == user.id)
    if plan_date is not None:
        query = query.filter(Task.plan_date == plan_date)
    subjects = {e.id: e.subject for e in db.query(Exam).filter(Exam.user_id == user.id).all()}
    overlaps = find_overlaps(query.all(), subjects=subjects)
    return {'count': len(overlaps), 'overlaps': overlaps, 'note': '相接时段不重叠；未定时任务只检查日预算，不推测时间。'}


@router.put("/{task_id}", response_model=TaskOut, summary="编辑任务（2.6：修改名称/日期/时长/优先级/科目）")
def update_task(
    task_id: int,
    payload: TaskUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return task_service.update_task(db, user.id, task_id, payload)


@router.post('/{task_id}/move/preview', response_model=TaskMovePreviewOut, summary='只读预览日历单项移动')
def preview_move(task_id: int, payload: TaskMoveIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return task_moves.preview_move(db, user.id, task_id, payload)


@router.post('/{task_id}/move', response_model=TaskOut, summary='保留时长移动任务，快照与冲突重验后保存')
def move_task(task_id: int, payload: TaskMoveIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return task_moves.apply_move(db, user.id, task_id, payload)


@router.post("/{task_id}/checkin", response_model=TaskOut, summary="打卡完成")
def checkin(
    task_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    lock_schedule(db, user.id, auth_key=user.auth_key)
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
    lock_schedule(db, user.id, auth_key=user.auth_key)
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
    return task_service.delete_tasks(db, user.id, task_id)


@router.delete('/{task_id}/series', summary='删除从本次日期起未完成的重复任务，保留完成记录')
def delete_remaining_series(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return task_service.delete_tasks(db, user.id, task_id, remaining_series=True)
