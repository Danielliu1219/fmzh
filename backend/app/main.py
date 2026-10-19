"""FastAPI 应用入口"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401  确保表模型注册到 Base
from .config import UPLOAD_DIR
from .database import Base, engine
from .routers import admin, ai, auth, collections, dashboard, exams, features, focus, materials, tasks

# 启动时建表（SQLite 无迁移，MVP 阶段够用；改表结构删除 fmzh.db 重建即可）
Base.metadata.create_all(bind=engine)


def _ensure_material_weight_column() -> None:
    """旧库补 materials.weight 列并按来源层级回填默认权重（用例 4.2）

    create_all 只建新表、不改旧表；这里做一次轻量迁移，避免为了新字段清库。
    """
    from sqlalchemy import text

    from .database import SessionLocal
    from .services.material_weight import default_weight_for

    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as conn:
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(materials)"))}
        if "weight" not in columns:
            conn.execute(text("ALTER TABLE materials ADD COLUMN weight FLOAT"))
    with SessionLocal() as db:
        pending = db.query(models.Material).filter(models.Material.weight.is_(None)).all()
        for material in pending:
            material.weight = default_weight_for(material.source_type)
        if pending:
            db.commit()


_ensure_material_weight_column()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="期末周别慌！API", version="0.1.0")

# 开发阶段放开跨域，部署时再收紧
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
app.include_router(exams.router, prefix="/api/exams", tags=["考试"])
app.include_router(materials.router, prefix="/api/materials", tags=["资料"])
app.include_router(collections.router, prefix="/api/collections", tags=["收藏与错题本"])
app.include_router(ai.router, prefix="/api/ai", tags=["AI 分析"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["任务"])
app.include_router(focus.router, prefix="/api/focus", tags=["番茄钟"])
app.include_router(dashboard.router, prefix="/api", tags=["首页与统计"])
app.include_router(features.router, prefix="/api/features", tags=["特色功能"])
app.include_router(admin.router, prefix="/api/admin", tags=["管理端"])

@app.get("/health", summary="健康检查")
def health():
    return {"status": "ok"}
