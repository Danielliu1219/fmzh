"""操作日志工具（9.4）：关键操作统一写入 operation_logs 表。

调用方与业务数据共用一次 commit；需要独立落库时传 commit=True。
"""
from sqlalchemy.orm import Session

from ..models.models import OperationLog, User


def log_operation(
    db: Session,
    action: str,
    user: User | None = None,
    *,
    username: str = "",
    target_type: str = "",
    target_id: int | None = None,
    detail: str = "",
    commit: bool = False,
) -> None:
    db.add(
        OperationLog(
            user_id=user.id if user is not None else None,
            username=(user.username if user is not None else username)[:32],
            action=action[:32],
            target_type=target_type[:32],
            target_id=target_id,
            detail=(detail or "")[:512],
        )
    )
    if commit:
        db.commit()
