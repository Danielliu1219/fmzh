import json
from typing import Literal, Any
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session, sessionmaker
from ..database import get_db
from ..models.models import AIJob, User, QaConversation, Exam
from ..utils.security import get_current_user
from ..schemas.schemas import (
    ProfileRequest,
    AnalyzeRequest,
    QaAskIn,
    WeeklyReportRequest,
)
from ..services import ai_jobs, model_usage
from ..services.task_conflicts import lock_schedule

router = APIRouter()


class Submit(BaseModel):
    kind: Literal["profile", "analysis", "qa", "weekly"]
    request_key: str = Field(min_length=1, max_length=64, pattern="^[A-Za-z0-9-]+$")
    payload: dict[str, Any]


@router.get("/limits")
def limits(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from ..config import settings
    return {**model_usage.limits(db, user.id),
        'analysis_max_tokens': None,
        'analysis_timeout_seconds': settings.LLM_ANALYSIS_TIMEOUT_SECONDS}


@router.post("/jobs", status_code=202)
def submit(
    payload: Submit,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if len(json.dumps(payload.payload, ensure_ascii=False)) > 50000:
        raise HTTPException(422, "输入内容过长，请缩短后重试")
    data = payload.payload
    try:
        if payload.kind == "qa":
            message = QaAskIn.model_validate(data)
            conversation_id = int(data.get("conversation_id", 0))
            if (
                not db.query(QaConversation.id)
                .filter(
                    QaConversation.id == conversation_id,
                    QaConversation.user_id == user.id,
                )
                .first()
            ):
                raise HTTPException(404, "问答会话不存在")
            data = {"conversation_id": conversation_id, **message.model_dump(mode='json', exclude_none=True)}
        else:
            model = {
                "profile": ProfileRequest,
                "analysis": AnalyzeRequest,
                "weekly": WeeklyReportRequest,
            }[payload.kind]
            data = model.model_validate(data).model_dump(mode="json")
            if (
                payload.kind != "weekly"
                and not db.query(Exam.id)
                .filter(Exam.id == data["exam_id"], Exam.user_id == user.id)
                .first()
            ):
                raise HTTPException(404, "考试不存在")
    except (ValidationError, ValueError, TypeError):
        raise HTTPException(422, "任务参数不合法，请检查输入")
    lock_schedule(db, user.id, auth_key=user.auth_key)
    digest = ai_jobs.payload_hash(payload.kind, data)
    existing = (
        db.query(AIJob)
        .filter_by(user_id=user.id, request_key=payload.request_key)
        .first()
    )
    if existing:
        if existing.payload_hash != digest:
            raise HTTPException(409, "同一请求标识不能用于不同任务")
        request.state.audit_target = existing.id
        return ai_jobs.output(existing)
    if (
        db.query(AIJob)
        .filter(AIJob.user_id == user.id, AIJob.status.in_(["queued", "running"]))
        .count()
        >= 2
    ):
        raise HTTPException(429, "已有大模型任务正在处理，请等待完成")
    # 在账号写锁内捕获资源生命周期；重试哈希仍只依赖客户端参数。
    stored_data = dict(data)
    if payload.kind != "weekly":
        resource_model = QaConversation if payload.kind == "qa" else Exam
        resource_id = (
            data["conversation_id"] if payload.kind == "qa" else data["exam_id"]
        )
        resource = (
            db.query(resource_model)
            .filter(resource_model.id == resource_id, resource_model.user_id == user.id)
            .populate_existing()
            .first()
        )
        if resource is None:
            raise HTTPException(404, "科目或问答会话已不存在")
        stored_data["_resource_created_at"] = resource.created_at.isoformat()
    job = AIJob(
        user_id=user.id,
        auth_key=user.auth_key,
        kind=payload.kind,
        request_key=payload.request_key,
        payload_hash=digest,
        payload_json=json.dumps(stored_data, ensure_ascii=False),
        request_id=getattr(request.state, "request_id", ""),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    request.state.audit_target = job.id
    result = ai_jobs.output(job)
    ai_jobs.enqueue(sessionmaker(bind=db.get_bind()), job.id)
    return result


@router.get("/jobs/{job_id}")
def get(
    job_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    job = db.query(AIJob).filter_by(id=job_id, user_id=user.id).first()
    if not job:
        raise HTTPException(404, "任务不存在")
    return ai_jobs.output(job)
