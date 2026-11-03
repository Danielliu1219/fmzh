"""FastAPI 应用入口"""
import os
import logging
import traceback
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401  确保表模型注册到 Base
from .config import UPLOAD_DIR, settings
from .database import Base, engine, SessionLocal
from .services.daily_pressure import make_lifespan
from .routers import admin, ai, auth, collections, dashboard, exams, features, focus, materials, notifications, study, tasks, quizzes, jobs
from .routers import study_sources
from .services.schema_upgrade import upgrade_schema
from .services.audit import AuditMiddleware
from .services.backups import runner as backup_runner
from .runtime import attach_frontend, cors_origins, prepare

# 创建缺失的表；每日压力记录等新表无需清空数据库或修改已有表的列。
prepare(settings)
Base.metadata.create_all(bind=engine)
upgrade_schema(engine)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="期末周别慌！API", version="0.1.0", lifespan=make_lifespan(SessionLocal, backup=backup_runner(engine,UPLOAD_DIR,settings)))

@app.exception_handler(Exception)
async def unexpected_error(request, exc):
    from fastapi.responses import JSONResponse
    request_id = getattr(request.state,'request_id','')
    frames = [(os.path.basename(f.filename),f.lineno,f.name) for f in traceback.extract_tb(exc.__traceback__)]
    logging.getLogger(__name__).error('request_id=%s exception=%s frames=%s',request_id,type(exc).__name__,frames)
    return JSONResponse(status_code=500,content={'detail':{'message':'请求未完成，请重试或联系管理员','request_id':request_id}},headers={'X-Request-ID':request_id})

# 完整应用同源访问；独立开发仅允许本机Vite，额外来源通过进程环境显式配置。
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(bool(os.environ.get('FMZH_FRONTEND_DIR'))),
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuditMiddleware)

app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
app.include_router(exams.router, prefix="/api/exams", tags=["考试"])
app.include_router(materials.router, prefix="/api/materials", tags=["资料"])
app.include_router(study_sources.router, prefix="/api/study-sources", tags=["复习来源"])
app.include_router(collections.router, prefix="/api/collections", tags=["收藏与错题本"])
app.include_router(ai.router, prefix="/api/ai", tags=["AI 分析"])
app.include_router(jobs.router,prefix='/api/ai',tags=['大模型任务'])
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
    state = getattr(app.state, 'daily_pressure', {'running': False})
    public = {key: state[key] for key in ('running', 'timezone', 'scheduled_time', 'poll_seconds', 'last_poll_at') if key in state}
    public['degraded'] = bool(state.get('failed', 0))
    return {"status": "ok", "daily_pressure": public, "backup":getattr(app.state,'backup',{'enabled':False})}


if os.environ.get('FMZH_FRONTEND_DIR'):
    attach_frontend(app, os.environ['FMZH_FRONTEND_DIR'])
