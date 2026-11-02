"""数据库连接：SQLite + SQLAlchemy"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

from .config import settings
from .runtime import database_url

# SQLite 相对路径统一转成绝对路径（相对 backend/ 目录）
url = database_url(settings.DATABASE_URL)

def make_engine(value):
    options = dict(pool_pre_ping=True)
    if value.get_backend_name() == 'sqlite':
        # 文件SQLite不等待小连接池，避免依赖会话、业务线程与审计线程互相占满。
        options.update(connect_args={'check_same_thread':False},
                       poolclass=StaticPool if value.database in (None,'',':memory:') else NullPool)
    else:
        options.update(pool_size=20,max_overflow=40,pool_timeout=1)
    return create_engine(value,**options)


engine = make_engine(url)
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
