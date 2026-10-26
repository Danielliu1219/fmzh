"""管理端接口（模块 8）：课程/科目维护、异常账号与违规内容治理

所有接口均要求管理员身份（依赖 get_current_admin）。
"""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.models import Course, Exam, Material, OperationLog, User
from ..schemas.schemas import (
    AdminMaterialOut,
    AdminUserOut,
    CourseCreate,
    CourseOut,
    CourseUpdate,
)
from ..utils.security import get_current_admin

router = APIRouter()


@router.get("/operation-logs", summary="管理员分页查询关键操作日志")
def operation_logs(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    actor: str = Query('', max_length=64), action: str = Query('', max_length=48),
    outcome: str = Query('', pattern='^(success|failure)?$'),
    date_from: date | None = None, date_to: date | None = None,
    _: User = Depends(get_current_admin), db: Session = Depends(get_db),
):
    from ..services.audit import ACTION_LABELS
    if action and action not in ACTION_LABELS:
        raise HTTPException(422, "未知操作类型")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "起始日期不能晚于结束日期")
    query = db.query(OperationLog)
    if actor.strip(): query = query.filter(OperationLog.actor_name.contains(actor.strip(), autoescape=True))
    if action: query = query.filter(OperationLog.action == action)
    if outcome == 'success': query = query.filter(OperationLog.status_code < 400)
    if outcome == 'failure': query = query.filter(OperationLog.status_code >= 400)
    def boundary(day):
        return datetime.combine(day, time.min, tzinfo=ZoneInfo('Asia/Shanghai')).astimezone(timezone.utc).replace(tzinfo=None)
    if date_from: query = query.filter(OperationLog.created_at >= boundary(date_from))
    if date_to: query = query.filter(OperationLog.created_at < boundary(date_to + timedelta(days=1)))
    total = query.count()
    rows = query.order_by(OperationLog.id.desc()).offset((page-1)*page_size).limit(page_size).all()
    return dict(total=total, page=page, page_size=page_size,
                actions=[dict(value=key, label=value) for key, value in ACTION_LABELS.items()],
                items=[dict(id=row.id, actor_id=row.actor_id, actor_name=row.actor_name,
                            action=row.action, label=ACTION_LABELS.get(row.action, row.action), target_id=row.target_id,
                            method=row.method, path=row.path, status_code=row.status_code,
                            outcome='success' if row.status_code < 400 else 'failure',
                            created_at=row.created_at.replace(tzinfo=timezone.utc)) for row in rows])


# ==================== 8.1 课程/科目维护 ====================

@router.get("/courses", response_model=list[CourseOut], summary="课程/科目列表")
def list_courses(_: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    return db.query(Course).order_by(Course.id).all()


@router.post("/courses", response_model=CourseOut, summary="新增课程/科目")
def create_course(
    payload: CourseCreate,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    course = Course(**payload.model_dump())
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


def _get_course(db: Session, course_id: int) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课程/科目不存在")
    return course


@router.put("/courses/{course_id}", response_model=CourseOut, summary="修改课程/科目")
def update_course(
    course_id: int,
    payload: CourseUpdate,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    course = _get_course(db, course_id)
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(course, field, value)
    db.commit()
    db.refresh(course)
    return course


@router.delete("/courses/{course_id}", summary="删除课程/科目")
def delete_course(
    course_id: int,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    course = _get_course(db, course_id)
    db.delete(course)
    db.commit()
    return {"ok": True}


# ==================== 8.2 异常账号与违规内容治理 ====================

@router.get("/users", response_model=list[AdminUserOut], summary="账号列表（含考试/资料数）")
def list_users(_: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.id).all()
    exam_counts = dict(
        db.query(Exam.user_id, func.count(Exam.id)).group_by(Exam.user_id).all()
    )
    material_counts = dict(
        db.query(Material.user_id, func.count(Material.id)).group_by(Material.user_id).all()
    )
    return [
        AdminUserOut(
            id=u.id,
            username=u.username,
            nickname=u.nickname,
            student_no=u.student_no,
            major=u.major,
            grade=u.grade,
            is_admin=u.is_admin,
            is_banned=u.is_banned,
            exam_count=exam_counts.get(u.id, 0),
            material_count=material_counts.get(u.id, 0),
            created_at=u.created_at,
        )
        for u in users
    ]


def _get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return user


@router.post("/users/{user_id}/ban", summary="封禁异常账号")
def ban_user(
    user_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = _get_user(db, user_id)
    if user.id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能封禁自己")
    user.is_banned = True
    db.commit()
    return {"ok": True, "is_banned": True}


@router.post("/users/{user_id}/unban", summary="解除封禁")
def unban_user(
    user_id: int,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = _get_user(db, user_id)
    user.is_banned = False
    db.commit()
    return {"ok": True, "is_banned": False}


@router.get("/materials", response_model=list[AdminMaterialOut], summary="全站资料列表（内容治理）")
def list_materials(
    keyword: str = "",
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    query = db.query(Material, User.username).join(User, Material.user_id == User.id)
    if keyword:
        query = query.filter(Material.title.contains(keyword))
    return [
        AdminMaterialOut(
            id=m.id,
            user_id=m.user_id,
            username=username,
            title=m.title,
            source_type=m.source_type,
            file_type=m.file_type,
            parse_status=m.parse_status,
            created_at=m.created_at,
        )
        for m, username in query.order_by(Material.id.desc()).all()
    ]


@router.delete("/materials/{material_id}", summary="删除违规内容")
def delete_material(
    material_id: int,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    from ..services.deletion import delete_material as remove
    return remove(db, material_id)


@router.post("/file-cleanups/retry", summary="重试提交后尚未完成的上传文件清理")
def retry_cleanups(_: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    from ..services.deletion import retry_file_cleanup
    return retry_file_cleanup(db)
