"""AI 接口（项目核心流程）

第一次调用：自然语言 -> 固定 JSON 用户画像（/profile）
第二次调用：画像 + 资料文本 -> 复习分析（/analyze）

LLM_MOCK=true 时使用 prompts.py 中的 Mock 实现，无需 API Key。
"""
import json

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models.models import Analysis, Exam, Material, User, UserProfile
from ..schemas.schemas import (
    AnalysisOut,
    AnalysisResult,
    AnalyzeRequest,
    ProfileOut,
    ProfileRequest,
)
from ..services import prompts
from ..services.llm_client import LLMError, chat_json
from ..services.plan_service import create_tasks_from_plan
from ..utils.security import get_current_user

router = APIRouter()

# 画像必填字段：缺任何一个都需要前端提示补全
PROFILE_REQUIRED = ["target", "learning_status", "available_days", "daily_hours"]
TARGETS = {"pass", "medium", "high"}
STATUSES = {"weak", "medium", "good"}

# 每次拼给大模型的资料文本上限：单份 6000 字、总计 30000 字
PER_MATERIAL_LIMIT = 6000
TOTAL_MATERIALS_LIMIT = 30000


def _get_own_exam(db: Session, user: User, exam_id: int) -> Exam:
    exam = db.query(Exam).filter(Exam.id == exam_id, Exam.user_id == user.id).first()
    if exam is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="考试不存在")
    return exam


def normalize_profile(data: dict) -> dict:
    """把大模型返回的画像数据归一化：过滤非法枚举、补默认值、计算缺失字段"""
    data = data or {}

    def pick(value, allowed):
        return value if value in allowed else None

    weak_chapters = data.get("weak_chapters")
    weak_chapters = [str(x) for x in weak_chapters][:20] if isinstance(weak_chapters, list) else []

    output_need = data.get("output_need")
    default_need = ["知识点权重", "复习计划", "自测题"]
    output_need = [str(x) for x in output_need] if isinstance(output_need, list) and output_need else default_need

    available_days = data.get("available_days")
    available_days = int(available_days) if isinstance(available_days, (int, float)) and not isinstance(available_days, bool) else None

    daily_hours = data.get("daily_hours")
    daily_hours = float(daily_hours) if isinstance(daily_hours, (int, float)) and not isinstance(daily_hours, bool) else None

    profile = {
        "target": pick(data.get("target"), TARGETS),
        "learning_status": pick(data.get("learning_status"), STATUSES),
        "available_days": available_days,
        "daily_hours": daily_hours,
        "weak_chapters": weak_chapters,
        "output_need": output_need,
    }
    profile["missing_fields"] = [f for f in PROFILE_REQUIRED if profile[f] is None]
    return profile


def _profile_to_text(profile: UserProfile) -> str:
    """画像 -> 给第二次调用用的文本描述"""
    target_map = {"pass": "保及格", "medium": "稳中等", "high": "冲高分"}
    status_map = {"weak": "基础薄弱", "medium": "基础一般", "good": "基础良好"}
    return (
        f"备考目标：{target_map.get(profile.target, '未填写')}；"
        f"基础水平：{status_map.get(profile.learning_status, '未填写')}；"
        f"剩余天数：{profile.available_days} 天；"
        f"每天可投入：{profile.daily_hours} 小时；"
        f"薄弱章节：{'、'.join(json.loads(profile.weak_chapters or '[]')) or '无'}；"
        f"期望输出：{'、'.join(json.loads(profile.output_need or '[]'))}"
    )


def _build_materials_text(materials: list[Material]) -> str:
    """拼接资料文本：每份标注 [来源类型]，超长截断"""
    parts = []
    total = 0
    for m in materials:
        text = (m.text_content or "").strip()
        if not text:
            continue
        text = text[:PER_MATERIAL_LIMIT]
        if total + len(text) > TOTAL_MATERIALS_LIMIT:
            text = text[: TOTAL_MATERIALS_LIMIT - total]
        parts.append(f"【{m.title}】[{m.source_type}]\n{text}")
        total += len(text)
        if total >= TOTAL_MATERIALS_LIMIT:
            break
    return "\n\n".join(parts)


@router.post("/profile", response_model=ProfileOut, summary="第一次调用：自然语言 -> 用户画像（不完整时返回缺失字段）")
def create_profile(
    payload: ProfileRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_own_exam(db, user, payload.exam_id)
    if not payload.raw_text.strip() and not (payload.supplement or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="请填写学习状态描述或补全内容"
        )

    # 取该科目最新画像：补全时在原文基础上追加，覆盖更新
    profile = (
        db.query(UserProfile)
        .filter(UserProfile.user_id == user.id, UserProfile.exam_id == payload.exam_id)
        .order_by(UserProfile.id.desc())
        .first()
    )
    if profile is None:
        profile = UserProfile(user_id=user.id, exam_id=payload.exam_id)
        db.add(profile)

    # 新描述优先；没传新描述时沿用已保存的描述；补全内容永远追加在末尾
    raw_text = payload.raw_text.strip() or profile.raw_text
    if payload.supplement and payload.supplement.strip():
        raw_text = f"{raw_text}\n补充说明：{payload.supplement.strip()}"
    profile.raw_text = raw_text

    exam = db.query(Exam).filter(Exam.id == payload.exam_id).first()
    try:
        if settings.LLM_MOCK:
            data = prompts.mock_extract_profile(raw_text)
        else:
            data = chat_json(
                prompts.PROFILE_SYSTEM_PROMPT,
                prompts.build_profile_user_prompt(exam.subject, raw_text),
                max_tokens=1000,
            )
    except LLMError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))

    data = normalize_profile(data)
    profile.target = data["target"]
    profile.learning_status = data["learning_status"]
    profile.available_days = data["available_days"]
    profile.daily_hours = data["daily_hours"]
    profile.weak_chapters = json.dumps(data["weak_chapters"], ensure_ascii=False)
    profile.output_need = json.dumps(data["output_need"], ensure_ascii=False)
    profile.is_complete = not data["missing_fields"]
    profile.missing_fields = json.dumps(data["missing_fields"], ensure_ascii=False)
    db.commit()

    return ProfileOut(
        exam_id=payload.exam_id,
        raw_text=raw_text,
        target=profile.target,
        learning_status=profile.learning_status,
        available_days=profile.available_days,
        daily_hours=profile.daily_hours,
        weak_chapters=data["weak_chapters"],
        output_need=data["output_need"],
        is_complete=profile.is_complete,
        missing_fields=data["missing_fields"],
    )


@router.post("/analyze", response_model=AnalysisOut, summary="第二次调用：画像 + 资料 -> 复习分析（并生成每日任务）")
def analyze(
    payload: AnalyzeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exam = _get_own_exam(db, user, payload.exam_id)

    profile = (
        db.query(UserProfile)
        .filter(UserProfile.user_id == user.id, UserProfile.exam_id == payload.exam_id)
        .order_by(UserProfile.id.desc())
        .first()
    )
    if profile is None or not profile.is_complete:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请先完成学习状态画像（/api/ai/profile），补全缺失字段后再生成分析",
        )

    materials = (
        db.query(Material)
        .filter(
            Material.user_id == user.id,
            Material.exam_id == payload.exam_id,
            Material.parse_status == "done",
        )
        .order_by(Material.id)
        .all()
    )
    materials_text = _build_materials_text(materials)
    if not materials_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该科目还没有可用的复习资料，请先上传 TXT/PDF/Word 资料",
        )

    # 最多尝试两次（大模型偶尔返回格式不对）
    last_err = None
    result = None
    for _ in range(2):
        try:
            if settings.LLM_MOCK:
                data = prompts.mock_generate_analysis(exam.subject, profile)
            else:
                data = chat_json(
                    prompts.ANALYZE_SYSTEM_PROMPT,
                    prompts.build_analyze_user_prompt(_profile_to_text(profile), materials_text),
                    max_tokens=4000,
                )
            result = AnalysisResult.model_validate(data)  # 校验大模型输出格式
            break
        except (LLMError, ValidationError) as e:
            last_err = e
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"AI 生成失败：{last_err}"
        )

    analysis = Analysis(
        user_id=user.id,
        exam_id=payload.exam_id,
        profile_id=profile.id,
        result_json=result.model_dump_json(),
        status="success",
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    # 复习计划 -> 每日任务（自动替换该科目旧的 AI 任务）
    create_tasks_from_plan(db, user.id, exam.id, analysis.id, result.review_plan)

    return AnalysisOut(
        id=analysis.id,
        exam_id=analysis.exam_id,
        status=analysis.status,
        result=result,
        created_at=analysis.created_at,
    )


@router.get("/analyses/{exam_id}", response_model=AnalysisOut, summary="获取某科目最新一次分析结果")
def latest_analysis(
    exam_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_own_exam(db, user, exam_id)
    analysis = (
        db.query(Analysis)
        .filter(Analysis.user_id == user.id, Analysis.exam_id == exam_id)
        .order_by(Analysis.id.desc())
        .first()
    )
    if analysis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该科目还没有分析结果")
    try:
        result = AnalysisResult.model_validate(json.loads(analysis.result_json))
    except (json.JSONDecodeError, ValidationError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="历史分析数据损坏")
    return AnalysisOut(
        id=analysis.id,
        exam_id=analysis.exam_id,
        status=analysis.status,
        result=result,
        created_at=analysis.created_at,
    )
