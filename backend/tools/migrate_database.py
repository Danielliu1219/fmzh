"""停写后把已升级的数据库复制到空目标库；连接信息只从环境变量读取。"""

import hashlib
import json
import os
import sys
from pathlib import Path
from sqlalchemy import create_engine, select, func

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.database import Base
from app.models import models  # noqa: F401  注册全部表模型


def digest(rows):
    return hashlib.sha256(
        json.dumps(
            rows, default=str, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


def copy_database(source, destination):
    """源库只读；禁止覆盖目标现有行，全部插入在同一事务中。"""
    Base.metadata.create_all(destination)
    result = {}
    with source.connect() as src, destination.begin() as dst:
        for table in Base.metadata.sorted_tables:
            if dst.scalar(select(func.count()).select_from(table)):
                raise ValueError("目标数据库必须为空：" + table.name)
        for table in Base.metadata.sorted_tables:
            order = list(table.primary_key.columns)
            rows = [
                dict(row)
                for row in src.execute(select(table).order_by(*order)).mappings()
            ]
            for offset in range(0, len(rows), 100):
                dst.execute(table.insert(), rows[offset : offset + 100])
            actual = [
                dict(row)
                for row in dst.execute(select(table).order_by(*order)).mappings()
            ]
            if digest(rows) != digest(actual):
                raise ValueError("数据摘要不一致：" + table.name)
            result[table.name] = dict(rows=len(rows), sha256=digest(rows))
    return result


if __name__ == "__main__":
    try:
        source = create_engine(os.environ["FMZH_SOURCE_DATABASE_URL"])
        destination = create_engine(os.environ["FMZH_TARGET_DATABASE_URL"])
        print(
            json.dumps(copy_database(source, destination), ensure_ascii=False, indent=2)
        )
    except Exception as exc:
        # 驱动异常可能含密码或数据，命令行只给异常类型。
        print("迁移失败，目标事务已回滚：" + type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)
