"""管理端接口（模块 8）：课程/科目维护、异常账号与违规内容治理

所有接口均要求管理员身份（依赖 get_current_admin）。
"""
from fastapi import APIRouter, Depends, HTTPException, status
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
    OperationLogOut,
)
from ..utils.operation_log import log_operation
from ..utils.security import get_current_admin

router = APIRouter()


# ==================== 8.1 课程/科目维护 ====================

@router.get("/courses", response_model=list[CourseOut], summary="课程/科目列表")
def list_courses(_: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    return db.query(Course).order_by(Course.id).all()


@router.post("/courses", response_model=CourseOut, summary="新增课程/科目")
def create_course(
    payload: CourseCreate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    course = Course(**payload.model_dump())
    db.add(course)
    db.flush()  # 先拿到课程 id 再记日志，二者同一次 commit
    log_operation(
        db, "新增课程", admin,
        target_type="course", target_id=course.id, detail=course.name,
    )
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
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    course = _get_course(db, course_id)
    changed = payload.model_dump(exclude_none=True)
    for field, value in changed.items():
        setattr(course, field, value)
    log_operation(
        db, "修改课程", admin,
        target_type="course", target_id=course.id,
        detail=f"{course.name}（字段：{', '.join(changed)}）",
    )
    db.commit()
    db.refresh(course)
    return course


@router.delete("/courses/{course_id}", summary="删除课程/科目")
def delete_course(
    course_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    course = _get_course(db, course_id)
    log_operation(
        db, "删除课程", admin,
        target_type="course", target_id=course.id, detail=course.name,
    )
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
    log_operation(
        db, "封禁账号", admin,
        target_type="user", target_id=user.id, detail=user.username,
    )
    db.commit()
    return {"ok": True, "is_banned": True}


@router.post("/users/{user_id}/unban", summary="解除封禁")
def unban_user(
    user_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = _get_user(db, user_id)
    user.is_banned = False
    log_operation(
        db, "解封账号", admin,
        target_type="user", target_id=user.id, detail=user.username,
    )
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
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    material = db.get(Material, material_id)
    if material is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资料不存在")
    log_operation(
        db, "删除违规资料", admin,
        target_type="material", target_id=material.id,
        detail=f"{material.title}（上传者 id={material.user_id}）",
    )
    db.delete(material)
    db.commit()
    return {"ok": True}


# ==================== 9.4 操作日志查询 ====================

@router.get("/logs", response_model=list[OperationLogOut], summary="操作日志（管理员可查）")
def list_logs(
    username: str = "",
    action: str = "",
    keyword: str = "",
    limit: int = 100,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    query = db.query(OperationLog)
    if username.strip():
        query = query.filter(OperationLog.username.contains(username.strip()))
    if action.strip():
        query = query.filter(OperationLog.action.contains(action.strip()))
    if keyword.strip():
        kw = keyword.strip()
        query = query.filter(
            OperationLog.detail.contains(kw)
            | OperationLog.action.contains(kw)
            | OperationLog.username.contains(kw)
        )
    limit = max(1, min(limit, 500))
    return query.order_by(OperationLog.id.desc()).limit(limit).all()
