"""数据库连接：SQLite + SQLAlchemy"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import BASE_DIR, settings

# SQLite 相对路径统一转成绝对路径（相对 backend/ 目录）
url = settings.DATABASE_URL
if url.startswith("sqlite:///") and url != "sqlite:///:memory:":
    db_path = url.replace("sqlite:///", "")
    url = f"sqlite:///{(BASE_DIR / db_path).as_posix()}"

engine = create_engine(
    url,
    # SQLite 多线程访问需要关掉同线程检查
    connect_args={"check_same_thread": False} if url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """所有表模型的基类"""


def get_db():
    """FastAPI 依赖：每个请求一个数据库会话，用完自动关闭"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
