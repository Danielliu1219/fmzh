"""认证接口：注册 / 登录（含连续失败锁定）/ 找回密码 / 修改密码 / 个人信息 / 注销账号

账号管理用例（FMZH-SRS）：
- 1.2 登录：连续 3 次失败锁定账号
- 1.3 锁定与解锁：锁定期 30 分钟自动解锁；经密码找回验证后立即解锁
- 1.4 密码找回：账号 + 学号验证身份 → 重置密码（前端二次确认）→ 自动解锁
- 1.5 修改密码：登录态验证原密码后设置新密码
- 1.7 注销账号：清理或匿名化该用户全部数据（含上传文件）
"""
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, union_all
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import UPLOAD_DIR
from ..database import Base, get_db
from ..models.models import Analysis, Exam, FocusGoal, FocusSession, Material, StudySetting, Task, User, UserProfile
from ..models.models import Notification, NotificationPreference, Reminder, Collection, MoodRecord, QuizAttempt
from ..models.models import QaConversation, QaMessage
from ..schemas.schemas import (
    ChangePasswordRequest,
    ResetConfirmRequest,
    ResetVerifyRequest,
    TokenResponse,
    UserLogin,
    UserOut,
    UserRegister,
    UserUpdate,
)
from ..utils.security import (
    create_access_token,
    create_reset_token,
    decode_reset_token,
    get_current_user,
    hash_password,
    verify_password,
)

router = APIRouter()

# 1.2/1.3 锁定口径：连续失败 3 次锁定，锁定期 30 分钟后自动解锁
MAX_FAILED_ATTEMPTS = 3
LOCK_MINUTES = 30


def _token_response(user: User) -> TokenResponse:
    return TokenResponse(access_token=create_access_token(user), user=UserOut.model_validate(user))


def _locked_message(user: User) -> str:
    remain = user.locked_until - datetime.now()
    minutes = max(int((remain.total_seconds() + 59) // 60), 1)  # 向上取整，至少 1 分钟
    return f"账号已锁定，请约 {minutes} 分钟后再试，或通过「找回密码」验证身份后立即解锁"


@router.post("/register", response_model=TokenResponse, summary="注册（成功即自动登录）")
def register(payload: UserRegister, db: Session = Depends(get_db)):
    exists = db.query(User).filter(User.username == payload.username).first()
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="账号已存在，请换一个账号")
    user = User(
        username=payload.username,
        hashed_password=hash_password(payload.password),
        nickname=payload.nickname or payload.username,
        student_no=payload.student_no,
        major=payload.major,
        grade=payload.grade,
    )
    # 老库可能残留已注销账号的数据。新账号跳过所有业务表出现过的 ID，防继承历史孤立数据。
    ids = union_all(select(User.id.label("used_id")), *[
        select(table.c.user_id.label("used_id")) for table in Base.metadata.tables.values() if "user_id" in table.c
    ]).subquery()
    for retry in range(3):
        user.id = (db.scalar(select(func.max(ids.c.used_id))) or 0) + 1
        try:
            db.add(user)
            db.commit()
            break
        except IntegrityError:
            db.rollback()
            if db.query(User).filter(User.username == payload.username).first():
                raise HTTPException(409, "账号已存在，请换一个账号")
            if retry == 2:
                raise HTTPException(409, "注册请求冲突，请重试")
    db.refresh(user)
    return _token_response(user)


@router.post("/login", response_model=TokenResponse, summary="登录（连续 3 次失败锁定 30 分钟）")
def login(payload: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码错误")

    # 1.3 锁定判定：锁定期内拒绝登录；到期自动解锁
    if user.locked_until is not None:
        if datetime.now() < user.locked_until:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_locked_message(user))
        user.locked_until = None
        user.failed_attempts = 0
        db.commit()

    if not verify_password(payload.password, user.hashed_password):
        user.failed_attempts = (user.failed_attempts or 0) + 1
        if user.failed_attempts >= MAX_FAILED_ATTEMPTS:
            # 1.2 连续 3 次失败：锁定账号，提示找回或等待解锁
            user.locked_until = datetime.now() + timedelta(minutes=LOCK_MINUTES)
            user.failed_attempts = 0
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"密码连续错误 {MAX_FAILED_ATTEMPTS} 次，账号已锁定 {LOCK_MINUTES} 分钟，可先「找回密码」立即解锁",
            )
        remain_failures = MAX_FAILED_ATTEMPTS - user.failed_attempts
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"账号或密码错误（连续错误 {user.failed_attempts}/{MAX_FAILED_ATTEMPTS} 次，再错 {remain_failures} 次将锁定账号）",
        )
    if user.is_banned:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="账号已被封禁，请联系管理员"
        )

    # 登录成功：清零失败计数与锁定状态
    user.failed_attempts = 0
    user.locked_until = None
    db.commit()
    return _token_response(user)


@router.post("/change-password", response_model=UserOut, summary="修改密码（1.5：验证原密码后设置新密码）")
def change_password(
    payload: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.old_password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="原密码不正确")
    if payload.old_password == payload.new_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="新密码不能与原密码相同")
    changed = db.query(User).filter(User.id == user.id, User.auth_key == user.auth_key).update({
        User.hashed_password: hash_password(payload.new_password), User.auth_key: uuid4().hex,
        User.failed_attempts: 0, User.locked_until: None,
    }, synchronize_session=False)
    if changed != 1:
        db.rollback()
        raise HTTPException(401, "登录已失效，请重新登录")
    db.commit()
    db.refresh(user)
    return user


@router.post("/reset-password/verify", summary="找回密码第一步：账号+学号验证身份（1.4）")
def reset_verify(payload: ResetVerifyRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    if user is None or not user.student_no or user.student_no != payload.student_no.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="账号与学号不匹配，验证失败")
    return {
        "reset_token": create_reset_token(user),
        "nickname": user.nickname or user.username,
        "locked": user.locked_until is not None and datetime.now() < user.locked_until,
        "message": "身份验证通过，请设置新密码（10 分钟内有效）",
    }


@router.post("/reset-password/confirm", summary="找回密码第二步：重置密码并解锁账号（1.4）")
def reset_confirm(payload: ResetConfirmRequest, db: Session = Depends(get_db)):
    user = decode_reset_token(payload.reset_token, db)
    changed = db.query(User).filter(User.id == user.id, User.auth_key == user.auth_key).update({
        User.hashed_password: hash_password(payload.new_password), User.auth_key: uuid4().hex,
        User.failed_attempts: 0, User.locked_until: None,
    }, synchronize_session=False)
    if changed != 1:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="找回链接已失效，请重新验证")
    db.commit()
    return {"ok": True, "message": "密码重置成功，账号已解锁，请使用新密码登录"}


@router.post("/logout", summary="退出并撤销该账号已有登录与找回凭证")
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    changed = db.query(User).filter(User.id == user.id, User.auth_key == user.auth_key).update({User.auth_key: uuid4().hex}, synchronize_session=False)
    if changed != 1:
        db.rollback()
        raise HTTPException(401, "登录已失效，请重新登录")
    db.commit()
    return {"ok": True}


@router.get("/me", response_model=UserOut, summary="获取当前用户信息")
def me(user: User = Depends(get_current_user)):
    return user


@router.put("/me", response_model=UserOut, summary="修改个人资料（1.6）")
def update_me(
    payload: UserUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/me", summary="注销账号（1.7：二次确认后清理全部个人数据，含上传文件）")
def deactivate_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # 先锁定并核对账号身份，防注销与 ID 重建并发时误删新账号。
    owned = db.query(User).filter(User.id == user.id, User.auth_key == user.auth_key).update({User.auth_key: user.auth_key}, synchronize_session=False)
    if owned != 1:
        db.rollback()
        raise HTTPException(401, "登录已失效，请重新登录")
    # 只删除上传根目录内、属于该账号的文件，异常路径不允许越界删除。
    materials = db.query(Material).filter(Material.user_id == user.id).all()
    root = UPLOAD_DIR.resolve()
    paths = []
    for material in materials:
        path = Path(material.file_path).resolve()
        if not path.is_relative_to(root) or path == root:
            raise HTTPException(409, "上传文件路径异常，请联系管理员处理")
        if path.exists() and not path.is_file():
            raise HTTPException(409, "上传文件路径异常，请联系管理员处理")
        if db.query(Material).filter(Material.file_path == material.file_path, Material.user_id != user.id).first() is None:
            paths.append(path)  # 演示库可能多用户共用同一文件，仍有引用时保留。
    for path in paths:
        path.unlink(missing_ok=True)
    user_dir = UPLOAD_DIR / str(user.id)
    if user_dir.exists() and not any(user_dir.iterdir()):
        user_dir.rmdir()

    # 清理该用户全部业务数据（需求口径：清理或匿名化，此处物理删除）
    for model in (Notification, Reminder, NotificationPreference, StudySetting, FocusSession, FocusGoal, Collection, MoodRecord, QuizAttempt, Task, Analysis, UserProfile):
        db.query(model).filter(model.user_id == user.id).delete()
    # 资料问答（4.5）：先删消息再删会话
    conversation_ids = [
        row[0]
        for row in db.query(QaConversation.id).filter(QaConversation.user_id == user.id).all()
    ]
    if conversation_ids:
        db.query(QaMessage).filter(QaMessage.conversation_id.in_(conversation_ids)).delete(
            synchronize_session=False
        )
    db.query(QaConversation).filter(QaConversation.user_id == user.id).delete()
    db.query(Material).filter(Material.user_id == user.id).delete()
    db.query(Exam).filter(Exam.user_id == user.id).delete()
    db.delete(user)  # users 表记录随注销删除，同账号名可重新注册
    db.commit()
    return {"ok": True, "message": "账号已注销，个人数据已清理"}
