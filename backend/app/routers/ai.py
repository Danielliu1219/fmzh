"""AI 接口（项目核心流程）

第一次调用：自然语言 -> 固定 JSON 用户画像（/profile）
第二次调用：画像 + 资料文本 -> 复习分析（/analyze）

LLM_MOCK=true 时使用 prompts.py 中的 Mock 实现，无需 API Key。
"""
import json
from datetime import date, datetime, timedelta
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models.models import (
    Analysis,
    Collection,
    Exam,
    Material,
    QaConversation,
    QaMessage,
    Task,
    User,
    UserProfile,
)
from ..schemas.schemas import (
    AnalysisOut,
    AnalysisResult,
    AnalyzeRequest,
    MindmapOut,
    MasteryOut,
    PlanItem,
    ProfileOut,
    ProfileRequest,
    QaAskIn,
    QaConversationCreate,
    QaConversationOut,
    QaMessageOut,
    QuestionTypeStat,
    ReplanIn,
    ReplanOut,
    WeightChange,
)
from ..services import prompts
from ..services.llm_client import LLMError, chat_json, chat_text
from ..services.material_weight import default_weight_for
from ..services.plan_service import create_tasks_from_plan
from ..services.study_planner import daily_budget
from ..services.quizzes import public_analysis, prepare_questions
from ..services.score_targets import band_strategy, band_text
from ..services.study_cards import build_cards, build_mindmap
from ..utils.security import get_current_user

router = APIRouter()

# 画像必填字段：缺任何一个都需要前端提示补全
PROFILE_REQUIRED = ["target", "learning_status", "available_days", "daily_hours"]
TARGETS = {"pass", "medium", "high"}
STATUSES = {"weak", "medium", "good"}

# 每次拼给大模型的资料文本上限：单份 6000 字、总计 30000 字
PER_MATERIAL_LIMIT = 6000
TOTAL_MATERIALS_LIMIT = 30000

# 三档分级推荐策略（用例 4.11）：Mock 与真实大模型共用同一套确定性收口
TIER_LABELS = {"pass": "保及格", "medium": "稳中等", "high": "冲高分"}
TIER_SUMMARY = {
    "pass": "以拿到高频基础分为目标：优先必考基础内容，低频低权重知识点后置，不把时间花在偏难怪题上。",
    "medium": "以稳定拿到中档分为目标：基础与中频考点并重，兼顾薄弱章节，适量练习常见综合题。",
    "high": "以冲刺高分为目标：必考与常考全覆盖，加大综合题、难题和易错点训练。",
}
TIER_PLAN_HINT = {
    "pass": "保及格策略：只做基础题与必得分内容，遇到偏难题先跳过",
    "medium": "稳中等策略：基础题 + 常见综合题，薄弱章节单独加练",
    "high": "冲高分策略：限时综合题 + 难题 + 错题复盘",
}


def _append_once(text: str, addition: str) -> str:
    """追加说明，已包含则不重复追加"""
    text = (text or "").strip()
    if not addition or addition in text:
        return text
    return f"{text}；{addition}" if text else addition


def _with_basis(text: str, source: str) -> str:
    """用例 4.13：确保每条推荐都显式写出依据来源"""
    text = (text or "").strip()
    if "依据来源" in text:
        return text
    source = (source or "").strip()
    if not source:
        return _append_once(text, "依据来源：所上传复习资料")
    return _append_once(text, f"依据来源：{source}")


def apply_tier_strategy(result: AnalysisResult, profile: UserProfile) -> None:
    """按保及格/稳中等/冲高分三档调整推荐结果（用例 4.11）

    在提示词约束之外再做一次确定性收口，保证 Mock 演示与真实大模型输出都体现三档差异。
    """
    target = profile.target
    label = TIER_LABELS.get(target)
    if label is None:
        return

    # 按权重降序展示，权重高的优先复习
    result.knowledge_points.sort(key=lambda kp: kp.weight, reverse=True)
    for kp in result.knowledge_points:
        if target == "pass" and kp.weight < 0.6:
            # 保及格：低权重知识点后置，压缩建议时长
            kp.importance = "low"
            kp.suggest_hours = max(1, round(kp.suggest_hours * 0.6))
        elif target == "high" and kp.weight >= 0.6:
            # 冲高分：高权重知识点加大投入
            kp.suggest_hours = round(kp.suggest_hours * 1.2)

    # 计划天数与每日时长不超过画像约束
    if profile.available_days:
        result.review_plan = result.review_plan[: profile.available_days]
    max_minutes = max(1, int((profile.daily_hours or 3) * 60))
    for item in result.review_plan:
        item.estimated_minutes = max(1, min(item.estimated_minutes, max_minutes))
    if result.review_plan:
        result.review_plan[0].detail = _append_once(
            result.review_plan[0].detail, TIER_PLAN_HINT[target]
        )

    result.summary = f"【{label}策略】{TIER_SUMMARY[target]}{result.summary}".strip()


def ensure_recommendation_basis(result: AnalysisResult) -> None:
    """用例 4.13：知识点推荐理由与考点判断依据都补上明确的依据来源"""
    for kp in result.knowledge_points:
        kp.recommend_reason = _with_basis(kp.recommend_reason, kp.source)
    for focus in result.exam_focus:
        focus.basis = _with_basis(focus.basis, focus.source)


# 从考点描述推断题型的兜底关键词（用例 4.7）
QUESTION_TYPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "选择题": ("选择",),
    "填空题": ("填空",),
    "计算题": ("计算",),
    "证明题": ("证明",),
    "应用题": ("应用",),
    "简答题": ("简答", "论述", "问答"),
    "综合题": ("综合",),
}


def derive_question_types(result: AnalysisResult) -> None:
    """大模型未给出题型分布时，从考点描述推断一个保守分布"""
    counts: dict[str, int] = {}
    for focus in result.exam_focus:
        text = f"{focus.content}{focus.basis}"
        weight = focus.frequency if focus.frequency > 0 else 1
        # 一条考点只归入最先匹配到的题型，避免「导数应用」同时算进计算题和应用题
        for question_type, keywords in QUESTION_TYPE_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                counts[question_type] = counts.get(question_type, 0) + weight
                break
    total = sum(counts.values())
    if not total:
        return
    result.question_types = [
        QuestionTypeStat(
            type=question_type,
            count=count,
            frequency=round(count / total, 2),
            basis="根据分析中的考点描述推断",
            source="分析结果",
        )
        for question_type, count in sorted(
            counts.items(), key=lambda item: item[1], reverse=True
        )
    ]


def ensure_question_type_analysis(result: AnalysisResult) -> None:
    """用例 4.7：保证题型分布存在，并把高频考点排在前面"""
    if not result.question_types:
        derive_question_types(result)
    # 出现次数多的在前；同次数时必考优先
    result.exam_focus.sort(key=lambda f: (f.frequency, f.level == "must"), reverse=True)


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
        f"备考目标：{band_text(profile.target_band) or target_map.get(profile.target, '未填写')}；"
        f"基础水平：{status_map.get(profile.learning_status, '未填写')}；"
        f"剩余天数：{profile.available_days} 天；"
        f"每天可投入：{profile.daily_hours} 小时；"
        f"薄弱章节：{'、'.join(json.loads(profile.weak_chapters or '[]')) or '无'}；"
        f"期望输出：{'、'.join(json.loads(profile.output_need or '[]'))}；"
        f"用户补充描述（目标以以上分数区间为准）：{(profile.raw_text or '')[:3000]}"
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
        weight = m.weight if m.weight is not None else default_weight_for(m.source_type)
        parts.append(f"【{m.title}】[{m.source_type}｜资料权重 {weight:.2f}]\n{text}")
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
    # 滑条选中的区间为明确目标，不让模型将其重新猜回另一档。
    if payload.target_band:
        profile.target_band = payload.target_band
    elif payload.raw_text.strip():
        profile.target_band = None  # 旧客户端重填自然语言时，不沿用上一份明确目标。
    if profile.target_band:
        data["target"] = band_strategy(profile.target_band)
        data["missing_fields"] = [f for f in data["missing_fields"] if f != "target"]
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
        target_band=profile.target_band,
        learning_status=profile.learning_status,
        available_days=profile.available_days,
        daily_hours=profile.daily_hours,
        weak_chapters=data["weak_chapters"],
        output_need=data["output_need"],
        is_complete=profile.is_complete,
        missing_fields=data["missing_fields"],
    )


@router.get("/profile/{exam_id}", response_model=ProfileOut, summary="读取本科已保存画像，供重新描述与调整目标")
def saved_profile(exam_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_own_exam(db, user, exam_id)
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id, UserProfile.exam_id == exam_id).order_by(UserProfile.id.desc()).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="该科目还没有学习画像")
    return ProfileOut(
        exam_id=exam_id, raw_text=profile.raw_text or "", target=profile.target,
        target_band=profile.target_band, learning_status=profile.learning_status,
        available_days=profile.available_days, daily_hours=profile.daily_hours,
        weak_chapters=json.loads(profile.weak_chapters or "[]"),
        output_need=json.loads(profile.output_need or "[]"), is_complete=profile.is_complete,
        missing_fields=json.loads(profile.missing_fields or "[]"),
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

    # 先看所有考试再估算本科份额，避免每一科都占满同一份全科预算。
    all_exams = db.query(Exam).filter(Exam.user_id == user.id, Exam.exam_date >= date.today()).all()
    weights = {e.id: 1 / max(1, (e.exam_date - date.today()).days) for e in all_exams}
    budget = daily_budget(db, user.id)
    share = max(1, int(budget * weights.get(exam.id, 1) / max(sum(weights.values()), 1e-6)))
    remaining_days = max(1, (exam.exam_date - date.today()).days)
    planning_profile = SimpleNamespace(
        available_days=min(profile.available_days, remaining_days), daily_hours=share / 60,
        target=profile.target, learning_status=profile.learning_status,
        target_band=profile.target_band,
    )
    context = _profile_to_text(profile) + f"\n注意：每天可用 {budget} 分钟是所有科目合计。本科建议每天最多 {share} 分钟；计划天数最多 {planning_profile.available_days} 天。请据此生成本科内容，系统随后做跨科容量校验。\n全部考试：" + "；".join(f"{e.subject} {e.exam_date}" for e in all_exams)

    # 最多尝试两次（大模型偶尔返回格式不对）
    last_err = None
    result = None
    for _ in range(2):
        try:
            if settings.LLM_MOCK:
                data = prompts.mock_generate_analysis(exam.subject, planning_profile)
            else:
                data = chat_json(
                    prompts.ANALYZE_SYSTEM_PROMPT,
                    prompts.build_analyze_user_prompt(context, materials_text),
                    max_tokens=4000,
                )
            result = AnalysisResult.model_validate(data)  # 校验大模型输出格式
            prepare_questions([q.model_dump() for q in result.quiz])
            break
        except (LLMError, ValidationError, ValueError) as e:
            last_err = e
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"AI 生成失败：{last_err}"
        )

    # 三档推荐策略（4.11）、依据来源（4.13）与题型/高频考点（4.7）在落库前统一收口
    apply_tier_strategy(result, planning_profile)
    ensure_recommendation_basis(result)
    ensure_question_type_analysis(result)

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
    scheduling = create_tasks_from_plan(db, user.id, exam.id, analysis.id, result.review_plan)

    return AnalysisOut(
        id=analysis.id,
        exam_id=analysis.exam_id,
        status=analysis.status,
        result=public_analysis(result),
        created_at=analysis.created_at,
        scheduling=scheduling,
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
        result=public_analysis(result),
        created_at=analysis.created_at,
    )


@router.get("/analyses/{exam_id}/mastery", response_model=MasteryOut, summary="知识点自测掌握状态与作答依据")
def analysis_mastery(exam_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_own_exam(db, user, exam_id)
    analysis = db.query(Analysis).filter(Analysis.user_id == user.id, Analysis.exam_id == exam_id).order_by(Analysis.id.desc()).first()
    if analysis is None:
        raise HTTPException(404, "该科目还没有分析结果")
    try:
        result = AnalysisResult.model_validate_json(analysis.result_json)
    except ValueError:
        raise HTTPException(500, "历史分析数据损坏")
    from ..services.mastery import knowledge_mastery
    return MasteryOut(exam_id=exam_id, points=knowledge_mastery(db, user.id, exam_id, [point.name for point in result.knowledge_points]))


@router.get(
    "/analyses/{exam_id}/mindmap",
    response_model=MindmapOut,
    summary="思维导图与记忆卡片（用例 4.4）",
)
def analysis_mindmap(
    exam_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """基于最近一次分析结果与资料正文，生成提纲式思维导图与背诵卡片"""
    exam = _get_own_exam(db, user, exam_id)
    analysis = (
        db.query(Analysis)
        .filter(Analysis.user_id == user.id, Analysis.exam_id == exam_id)
        .order_by(Analysis.id.desc())
        .first()
    )
    if analysis is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="该科目还没有分析结果"
        )
    try:
        result = AnalysisResult.model_validate(json.loads(analysis.result_json))
    except (json.JSONDecodeError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="历史分析数据损坏"
        )

    materials = (
        db.query(Material)
        .filter(
            Material.user_id == user.id,
            Material.exam_id == exam_id,
            Material.parse_status == "done",
        )
        .order_by(Material.id)
        .all()
    )
    texts = [material.text_content or "" for material in materials]
    return MindmapOut(
        exam_id=exam_id,
        course=exam.subject,
        mindmap=build_mindmap(exam.subject, result, texts),
        cards=build_cards(result, texts),
    )


# ==================== 资料问答（用例 4.5） ====================

QA_HISTORY_LIMIT = 10  # 最多带上最近 10 条消息（约 5 轮）
QA_MATERIALS_LIMIT = 12000  # 问答时喂给大模型的资料正文上限


def _get_own_conversation(db: Session, user: User, conversation_id: int) -> QaConversation:
    conversation = (
        db.query(QaConversation)
        .filter(QaConversation.id == conversation_id, QaConversation.user_id == user.id)
        .first()
    )
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="问答会话不存在")
    return conversation


def _qa_conversation_out(
    db: Session, conversation: QaConversation, with_messages: bool = True
) -> QaConversationOut:
    messages = []
    if with_messages:
        rows = (
            db.query(QaMessage)
            .filter(QaMessage.conversation_id == conversation.id)
            .order_by(QaMessage.id)
            .all()
        )
        messages = [QaMessageOut.model_validate(row) for row in rows]
    return QaConversationOut(
        id=conversation.id,
        exam_id=conversation.exam_id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=messages,
    )


@router.get(
    "/qa/conversations",
    response_model=list[QaConversationOut],
    summary="资料问答会话列表（用例 4.5）",
)
def list_qa_conversations(
    exam_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(QaConversation).filter(QaConversation.user_id == user.id)
    if exam_id is not None:
        _get_own_exam(db, user, exam_id)
        query = query.filter(QaConversation.exam_id == exam_id)
    conversations = (
        query.order_by(QaConversation.updated_at.desc(), QaConversation.id.desc())
        .limit(20)
        .all()
    )
    return [_qa_conversation_out(db, item, with_messages=False) for item in conversations]


@router.post(
    "/qa/conversations",
    response_model=QaConversationOut,
    status_code=status.HTTP_201_CREATED,
    summary="新建资料问答会话（用例 4.5）",
)
def create_qa_conversation(
    payload: QaConversationCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exam = _get_own_exam(db, user, payload.exam_id)
    conversation = QaConversation(
        user_id=user.id,
        exam_id=exam.id,
        title=payload.title.strip() or f"{exam.subject} 资料问答",
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return _qa_conversation_out(db, conversation)


@router.get(
    "/qa/conversations/{conversation_id}",
    response_model=QaConversationOut,
    summary="读取资料问答会话与历史消息（用例 4.5）",
)
def get_qa_conversation(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation = _get_own_conversation(db, user, conversation_id)
    return _qa_conversation_out(db, conversation)


@router.delete("/qa/conversations/{conversation_id}", summary="删除资料问答会话（用例 4.5）")
def delete_qa_conversation(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation = _get_own_conversation(db, user, conversation_id)
    db.query(QaMessage).filter(QaMessage.conversation_id == conversation.id).delete()
    db.delete(conversation)
    db.commit()
    return {"ok": True}


@router.post(
    "/qa/conversations/{conversation_id}/messages",
    response_model=QaConversationOut,
    summary="资料问答：提问并保存多轮对话（用例 4.5）",
)
def ask_qa(
    conversation_id: int,
    payload: QaAskIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """把问题与历史对话一起发给大模型，回答写入会话，支持页面刷新后继续追问"""
    conversation = _get_own_conversation(db, user, conversation_id)
    exam = _get_own_exam(db, user, conversation.exam_id)
    question = payload.content.strip()
    if not question:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="问题不能为空")

    materials = (
        db.query(Material)
        .filter(
            Material.user_id == user.id,
            Material.exam_id == conversation.exam_id,
            Material.parse_status == "done",
        )
        .order_by(Material.id)
        .all()
    )
    materials_text = _build_materials_text(materials)[:QA_MATERIALS_LIMIT]
    if not materials_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该科目还没有可用的复习资料，请先上传 TXT/PDF/Word 资料",
        )

    # 先落用户问题，再取最近若干条消息作为多轮上下文
    db.add(QaMessage(conversation_id=conversation.id, role="user", content=question))
    db.flush()
    history_rows = (
        db.query(QaMessage)
        .filter(QaMessage.conversation_id == conversation.id)
        .order_by(QaMessage.id.desc())
        .limit(QA_HISTORY_LIMIT)
        .all()
    )
    history = [
        {"role": row.role, "content": row.content} for row in reversed(history_rows)
    ]

    try:
        if settings.LLM_MOCK:
            answer = prompts.mock_qa_answer(exam.subject, question, materials_text)
        else:
            answer = chat_text(
                prompts.build_qa_system_prompt(materials_text), history, max_tokens=1200
            )
    except LLMError as exc:
        db.rollback()  # 回答失败时不保留这条提问
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"AI 回答失败：{exc}"
        ) from exc

    db.add(QaMessage(conversation_id=conversation.id, role="assistant", content=answer))
    conversation.updated_at = datetime.now()
    db.commit()
    db.refresh(conversation)
    return _qa_conversation_out(db, conversation)


# ==================== 动态调整计划与权重（用例 4.12） ====================
@router.post("/analyses/{exam_id}/replan", response_model=ReplanOut, summary="按学习反馈预览并确认全科预算内的计划调整")
def replan_analysis(exam_id: int, payload: ReplanIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from ..services.replanning import replan
    return replan(db, user, exam_id, payload)
