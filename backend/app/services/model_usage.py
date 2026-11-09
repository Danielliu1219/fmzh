"""按用户/北京时间自然日记录真实HTTP调用。"""

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
        if row is None:
            row = ModelUsage(user_id=uid, usage_date=day, calls=0)
            db.add(row)
        row.calls += 1
        db.commit()


def limits(db, user_id):
    row = db.get(ModelUsage, (user_id, beijing_day()))
    used = row.calls if row else 0
    return dict(
        daily_limit=None,
        used_calls=used,
        remaining_calls=None,
        mock=settings.LLM_MOCK,
        timezone="Asia/Shanghai",
    )
