"""数据库连接：SQLite + SQLAlchemy"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings
from .runtime import database_url

# SQLite 相对路径统一转成绝对路径（相对 backend/ 目录）
url = database_url(settings.DATABASE_URL)

engine = create_engine(
    url,
    # SQLite 多线程访问需要关掉同线程检查
    connect_args={"check_same_thread": False} if url.get_backend_name() == 'sqlite' else {},
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
