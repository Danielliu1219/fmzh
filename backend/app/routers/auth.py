"""认证接口：注册 / 登录 / 个人信息"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.models import User
from ..schemas.schemas import TokenResponse, UserLogin, UserOut, UserRegister, UserUpdate
from ..utils.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)

router = APIRouter()


def _token_response(user: User) -> TokenResponse:
    return TokenResponse(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


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
    db.add(user)
    db.commit()
    db.refresh(user)
    return _token_response(user)


@router.post("/login", response_model=TokenResponse, summary="登录")
def login(payload: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码错误"
        )
    return _token_response(user)


@router.get("/me", response_model=UserOut, summary="获取当前用户信息")
def me(user: User = Depends(get_current_user)):
    return user


@router.put("/me", response_model=UserOut, summary="修改个人资料")
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
