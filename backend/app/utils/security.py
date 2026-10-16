"""认证工具：密码哈希、JWT、获取当前用户"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models.models import User

bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


# 密码找回令牌（1.4）：10 分钟有效，仅可用于重置密码
RESET_TOKEN_EXPIRE_MINUTES = 10


def create_reset_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "typ": "reset", "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def decode_reset_token(token: str) -> int:
    """校验找回令牌，返回 user_id；无效/过期/类型不符时抛 400"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="找回链接已失效，请重新验证")
    if payload.get("typ") != "reset":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="找回链接已失效，请重新验证")
    return int(payload["sub"])


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI 依赖：从 Authorization: Bearer <token> 解析当前登录用户"""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录或登录已过期"
        )
    try:
        payload = jwt.decode(credentials.credentials, settings.SECRET_KEY, algorithms=["HS256"])
        user_id = int(payload["sub"])
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="登录凭证无效，请重新登录"
        )
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    if user.is_banned:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="账号已被封禁，请联系管理员"
        )
    return user


def get_current_admin(user: User = Depends(get_current_user)) -> User:
    """FastAPI 依赖：要求当前用户是管理员（管理端 8.x）"""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限"
        )
    return user
