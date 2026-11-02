"""按用户/北京时间自然日计量真实HTTP调用；重试也计次，超额不发请求。"""

from contextvars import ContextVar
from functools import wraps
from inspect import signature
from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker
from ..models.models import ModelUsage, User
from ..config import settings
from .pressure import beijing_day

_context = ContextVar("model_usage_context", default=None)


def metered(function):
    params = signature(function)

    @wraps(function)
    def run(*args, **kwargs):
        bound = params.bind_partial(*args, **kwargs).arguments
        user, db = bound["user"], bound["db"]
        token = _context.set((user.id, user.auth_key, sessionmaker(bind=db.get_bind())))
        try:
            return function(*args, **kwargs)
        finally:
            _context.reset(token)

    return run


def reserve_call():
    context = _context.get()
    if context is None:
        return  # 独立传输测试/内部客户端调用，没有业务用户。
    uid, key, factory = context
    with factory() as db:
        if (
            not db.query(User)
            .filter(User.id == uid, User.auth_key == key)
            .update({User.id: uid}, synchronize_session=False)
        ):
            raise HTTPException(401, "会话已失效，本次未调用大模型")
        day = beijing_day()
        row = db.get(ModelUsage, (uid, day))
        limit = max(1, settings.LLM_DAILY_LIMIT)
        if row and row.calls >= limit:
            raise HTTPException(429, f"今日真实大模型调用已达{limit}次上限，请明天再试")
        if row is None:
            row = ModelUsage(user_id=uid, usage_date=day, calls=0)
            db.add(row)
        row.calls += 1
        db.commit()


def limits(db, user_id):
    row = db.get(ModelUsage, (user_id, beijing_day()))
    used = row.calls if row else 0
    limit = max(1, settings.LLM_DAILY_LIMIT)
    return dict(
        daily_limit=limit,
        used_calls=used,
        remaining_calls=max(0, limit - used),
        mock=settings.LLM_MOCK,
        timezone="Asia/Shanghai",
    )
