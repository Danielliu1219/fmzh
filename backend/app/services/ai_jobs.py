"""持久化的大模型任务；提交不等待模型，读取按账号隔离，重启不自动重放付费调用。"""

import hashlib
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Lock
from fastapi import HTTPException
from ..models.models import AIJob, User, OperationLog, Exam, QaConversation
from .task_conflicts import lock_schedule

_pool = None
_lock = Lock()
logger = logging.getLogger('uvicorn.error.jobs')


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def output(job):
    return dict(
        id=job.id,
        kind=job.kind,
        status=job.status,
        request_id=job.request_id,
        result=json.loads(job.result_json) if job.result_json else None,
        error=job.error_message,
        error_status=job.error_status,
    )


def enqueue(factory, job_id):
    global _pool
    with _lock:
        if _pool is None:
            _pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="model-job")
        _pool.submit(execute, factory, job_id)


def stop():
    global _pool
    with _lock:
        pool, _pool = _pool, None
    if pool:
        pool.shutdown(wait=True, cancel_futures=True)


def recover(factory):
    with factory() as db:
        db.query(AIJob).filter(AIJob.status.in_(["queued", "running"])).update(
            {
                AIJob.status: "failed",
                AIJob.error_status: 409,
                AIJob.error_message: "服务重启中断了任务，请先刷新已有结果，再决定是否重新生成",
                AIJob.payload_json: "{}",
                AIJob.auth_key: "",
                AIJob.finished_at: now(),
            },
            synchronize_session=False,
        )
        db.commit()


def execute(factory, job_id):
    started_at = time.perf_counter()
    from ..routers import ai, dashboard
    from ..schemas.schemas import (
        ProfileRequest,
        AnalyzeRequest,
        QaAskIn,
        WeeklyReportRequest,
    )

    actor_id = actor_name = request_id = kind = target = ""
    status_code = 200
    result = None
    error = ""
    with factory() as db:
        job = db.get(AIJob, job_id)
        if job is None or job.status != "queued":
            return
        job.status = "running"
        db.commit()
        kind, request_id = job.kind, job.request_id
        actor_id = job.user_id
        try:
            user = db.get(User, job.user_id)
            if (
                user is None
                or user.auth_key != job.auth_key
                or user.is_banned
                or (user.locked_until and user.locked_until > datetime.now())
            ):
                raise HTTPException(401, "会话或账号状态已变化，本次未执行大模型任务")
            actor_name = user.username
            payload = json.loads(job.payload_json)
            if kind != "weekly":
                lock_schedule(db, user.id, auth_key=user.auth_key)
                resource_model = QaConversation if kind == "qa" else Exam
                resource_id = (
                    payload["conversation_id"] if kind == "qa" else payload["exam_id"]
                )
                resource = (
                    db.query(resource_model)
                    .filter(
                        resource_model.id == resource_id,
                        resource_model.user_id == user.id,
                    )
                    .populate_existing()
                    .first()
                )
                if resource is None or resource.created_at.isoformat() != payload.pop(
                    "_resource_created_at", None
                ):
                    raise HTTPException(
                        409,
                        "原科目或问答会话已删除或替换，本次未调用大模型，请刷新后重新选择",
                    )
            if kind == "profile":
                result = ai.create_profile(
                    ProfileRequest.model_validate(payload), user=user, db=db
                )
            elif kind == "analysis":
                result = ai.analyze(
                    AnalyzeRequest.model_validate(payload), user=user, db=db
                )
            elif kind == "qa":
                result = ai.ask_qa(
                    payload["conversation_id"],
                    QaAskIn.model_validate(payload),
                    user=user,
                    db=db,
                )
            else:
                result = dashboard.weekly_report(
                    WeeklyReportRequest.model_validate(payload), user=user, db=db
                )
            target = str(
                getattr(result, "id", None)
                or payload.get("exam_id")
                or payload.get("conversation_id")
                or ""
            )
            result = (
                result.model_dump(mode="json")
                if hasattr(result, "model_dump")
                else result
            )
        except HTTPException as exc:
            db.rollback()
            status_code = exc.status_code
            error = (
                exc.detail.get("message", "任务未完成，请刷新数据")
                if isinstance(exc.detail, dict)
                else str(exc.detail)
            )
        except Exception as exc:
            db.rollback()
            status_code = 500
            error = "任务未完成，请刷新已有数据后重试"
            logger.error(
                "request_id=%s job_id=%s exception=%s",
                request_id,
                job_id,
                type(exc).__name__,
            )
    # 业务接口已有事务保护；完成信息单独持久化，不自动重复生成。
    for attempt in range(3):
        try:
            with factory() as db:
                job = db.get(AIJob, job_id)
                if job is None:
                    return  # 注销已清理任务，不能写回孤立数据。
                job.status = "succeeded" if status_code < 400 else "failed"
                job.result_json = (
                    json.dumps(result, ensure_ascii=False)
                    if status_code < 400
                    else None
                )
                job.error_message = error[:512]
                job.error_status = status_code if status_code >= 400 else 0
                job.payload_json = "{}"
                job.auth_key = ""
                job.finished_at = now()
                db.add(
                    OperationLog(
                        request_id=request_id,
                        actor_id=actor_id or None,
                        actor_name=actor_name,
                        action={
                            "analysis": "ai.analyze",
                            "profile": "ai.profile",
                            "qa": "ai.qa",
                            "weekly": "ai.weekly",
                        }[kind],
                        target_id=target,
                        method="POST",
                        path="/api/ai/jobs",
                        status_code=status_code,
                        created_at=now(),
                    )
                )
                db.commit()
            logger.info('model_job_finished job_id=%s kind=%s status=%s elapsed_seconds=%.3f', job_id, kind, status_code, time.perf_counter() - started_at)
            return
        except Exception as exc:
            logger.error(
                "job completion persistence request_id=%s job_id=%s attempt=%s exception=%s",
                request_id,
                job_id,
                attempt + 1,
                type(exc).__name__,
            )


def payload_hash(kind, payload):
    return hashlib.sha256(
        json.dumps([kind, payload], sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
