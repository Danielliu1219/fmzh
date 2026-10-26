"""FastAPI 应用入口"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401  确保表模型注册到 Base
from .config import UPLOAD_DIR
from .database import Base, engine
from .routers import admin, ai, auth, collections, dashboard, exams, features, focus, materials, notifications, study, tasks, quizzes
from .services.schema_upgrade import upgrade_schema
from .services.audit import AuditMiddleware

# 创建缺失的表；新增预算 / 提醒表无需清空数据库或修改已有表的列。
Base.metadata.create_all(bind=engine)
upgrade_schema(engine)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="期末周别慌！API", version="0.1.0")

# 开发阶段放开跨域，部署时再收紧
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuditMiddleware)

app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
app.include_router(exams.router, prefix="/api/exams", tags=["考试"])
app.include_router(materials.router, prefix="/api/materials", tags=["资料"])
app.include_router(collections.router, prefix="/api/collections", tags=["收藏与错题本"])
app.include_router(ai.router, prefix="/api/ai", tags=["AI 分析"])
app.include_router(quizzes.router, prefix="/api/quizzes", tags=["自测判分"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["任务"])
app.include_router(focus.router, prefix="/api/focus", tags=["番茄钟"])
app.include_router(study.router, prefix="/api/study", tags=["全科复习计划"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["站内提醒"])
app.include_router(dashboard.router, prefix="/api", tags=["首页与统计"])
app.include_router(features.router, prefix="/api/features", tags=["特色功能"])
app.include_router(admin.router, prefix="/api/admin", tags=["管理端"])

@app.get("/health", summary="健康检查")
def health():
    return {"status": "ok"}
