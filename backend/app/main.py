"""FastAPI 应用入口"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401  确保表模型注册到 Base
from .config import UPLOAD_DIR
from .database import Base, engine
from .routers import ai, auth, dashboard, exams, materials, tasks

# 启动时建表（SQLite 无迁移，MVP 阶段够用；改表结构删除 fmzh.db 重建即可）
Base.metadata.create_all(bind=engine)
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
app.include_router(ai.router, prefix="/api/ai", tags=["AI 分析"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["任务"])
app.include_router(dashboard.router, prefix="/api", tags=["首页与统计"])


@app.get("/health", summary="健康检查")
def health():
    return {"status": "ok"}
