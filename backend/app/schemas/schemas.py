"""Pydantic 请求/响应模型：前后端接口契约

字段含义、枚举取值与 docs/接口文档.md 保持一致。
"""
from datetime import date, datetime, time
from typing import Any, Optional, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, field_serializer
from ..services.score_targets import ScoreBand
from ..services.task_details import task_time

# ==================== 用户 ====================


class UserRegister(BaseModel):
    username: str = Field(min_length=3, max_length=20, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(min_length=6, max_length=32)
    nickname: str = ""
    student_no: str = ""
    major: str = ""
    grade: str = ""


class UserLogin(BaseModel):
    username: str
    password: str


class UserUpdate(BaseModel):
    nickname: Optional[str] = None
    student_no: Optional[str] = None
    major: Optional[str] = None
    grade: Optional[str] = None
    class_name: Optional[str] = None  # 班级（FMZH-USR-0005）
    avatar: Optional[str] = None  # 头像色值（预设色板），空串恢复默认


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    nickname: str
    student_no: str
    major: str
    grade: str
    is_admin: bool = False
    class_name: str = ""
    avatar: str = ""
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ==================== 账号安全（1.5 修改密码 / 1.4 密码找回 / 1.7 注销） ====================


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=32)


class ResetVerifyRequest(BaseModel):
    username: str
    student_no: str = Field(min_length=1, description="学号，用于身份验证")


class ResetConfirmRequest(BaseModel):
    reset_token: str
    new_password: str = Field(min_length=6, max_length=32)


# ==================== 考试 ====================


class ExamCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=64)
    exam_date: date
    location: str = ""
    duration_minutes: int = 120
    note: str = ""
    color: str = ""  # 科目颜色标签（2.11）


class ExamUpdate(BaseModel):
    subject: Optional[str] = None
    exam_date: Optional[date] = None
    location: Optional[str] = None
    duration_minutes: Optional[int] = None
    note: Optional[str] = None
    color: Optional[str] = None  # 科目颜色标签（2.11）


class ExamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subject: str
    exam_date: date
    location: str
    duration_minutes: int
    note: str
    color: str = ""
    created_at: datetime


# ==================== 资料 ====================


class MaterialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    exam_id: Optional[int]
    title: str
    source_type: str
    file_type: str
    parse_status: str
    description: str
    tags: str
    weight: float = 0.5  # 资料权重（用例 4.2），学生可手动调整
    default_weight: float = 0.5  # 当前来源类型对应的默认权重，供「恢复默认」使用
    weight_level: str = "中"  # 权重档位（用例 3.2）：高 / 中 / 低
    created_at: datetime
    snippet: str = ""  # 全文搜索命中片段（用例 3.4），仅带 keyword 查询时返回


class MaterialDetailOut(MaterialOut):
    text_preview: str = ""  # 解析文本前 1000 字


class SourceSuggestionOut(BaseModel):
    """系统辅助识别资料来源类型的建议（用例 3.2）"""

    source_type: str  # 七类来源之一，未识别时为「其他」
    confidence: str  # high / medium / low
    reason: str = ""  # 命中的文件名/正文关键词说明


class MaterialUpdate(BaseModel):
    """资料编辑 / 移动分类（用例 3.3）：字段均可选，只更新请求里出现的字段"""

    title: Optional[str] = None
    exam_id: Optional[int] = None  # 传 null 表示移出科目（回到「未归类」）
    source_type: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[str] = None
    weight: Optional[float] = Field(None, ge=0, le=1)  # 资料权重手动调整（用例 4.2）


class MaterialMergeIn(BaseModel):
    """合并导出复习笔记（用例 3.6）：勾选多份资料合并为一份"""

    material_ids: list[int] = Field(min_length=1)
    title: str = ""


class MaterialMergeOut(BaseModel):
    title: str
    markdown: str
    material_count: int
    total_chars: int
    warnings: list[str] = []  # 例如某份资料解析失败没有正文


# ==================== 收藏与错题本（用例 3.5） ====================


class CollectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_type: str  # material / question
    material_id: Optional[int]
    title: str
    content: str
    source: str  # manual / quiz
    created_at: datetime


class CollectionCreate(BaseModel):
    """手动收藏：收藏一份资料（item_type=material），或收藏一道题目（item_type=question）"""

    item_type: str
    material_id: Optional[int] = None
    title: str = ""
    content: str = ""


class MistakeItem(BaseModel):
    """一道答错的题（由 4.6 自测判分写入错题本）"""

    title: str  # 题干，同时用作错题本的展示标题与去重键
    content: str = ""  # 题目详情 JSON（选项/正确答案/解析/知识点）
    knowledge_point: str = ""


class MistakeBatchIn(BaseModel):
    mistakes: list[MistakeItem]


# ==================== AI 画像（第一次调用） ====================


class ProfileRequest(BaseModel):
    exam_id: int
    raw_text: str = ""  # 用户自然语言描述；补全时可为空串
    supplement: Optional[str] = None  # 补全内容，与已保存的 raw_text 合并后重新提取
    target_band: Optional[ScoreBand] = None


class ProfileOut(BaseModel):
    exam_id: int
    raw_text: str
    target: Optional[str] = None  # pass / medium / high
    target_band: Optional[ScoreBand] = None  # 川大成绩区间，旧画像可为空
    learning_status: Optional[str] = None  # weak / medium / good
    available_days: Optional[int] = None
    daily_hours: Optional[float] = None
    weak_chapters: list[str] = []
    output_need: list[str] = []
    is_complete: bool = False
    missing_fields: list[str] = []


# ==================== 资料问答（用例 4.5） ====================


class QaMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str  # user / assistant
    content: str
    created_at: datetime


class QaConversationOut(BaseModel):
    id: int
    exam_id: int
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[QaMessageOut] = []


class QaConversationCreate(BaseModel):
    exam_id: int
    title: str = ""


class QaAskIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


# ==================== AI 分析（第二次调用） ====================


class SourceReference(BaseModel):
    material_id: int
    quote: str = Field(default="", max_length=2000)
    start: Optional[int] = None
    end: Optional[int] = None
    content_hash: str = ""
    match: str = "quote"
    material_created_at: Optional[datetime] = None


class SourceExcerpt(BaseModel):
    material_id: int
    material_title: str = ""
    source_type: str = ""
    file_type: str = ""
    status: str  # available / changed / unavailable
    note: str = ""
    location: str = ""
    page: Optional[int] = None
    start: Optional[int] = None
    end: Optional[int] = None
    content_hash: str = ""
    context: str = ""
    highlight_start: int = 0
    highlight_end: int = 0
    match: str = "quote"
    material_created_at: Optional[datetime] = None


class EvidenceRequest(BaseModel):
    analysis_id: int = Field(ge=1)
    kind: str = Field(pattern="^(knowledge|focus|question_type)$")
    item_index: int = Field(ge=0, le=500)


class EvidenceOut(BaseModel):
    analysis_id: int
    exam_id: int
    item_title: str
    items: list[SourceExcerpt]
    note: str


class KnowledgePoint(BaseModel):
    name: str
    weight: float = Field(ge=0, le=1)
    importance: str = "medium"  # high / medium / low
    recommend_reason: str = ""
    source: str = ""  # 推荐依据来自哪类资料
    suggest_hours: float = 0  # 兼容旧客户端；精确分配以分钟为准
    suggest_minutes: Optional[int] = None
    practice_hint: str = ""
    citations: list[SourceReference] = []


class MasteryEvidence(BaseModel):
    question: str
    correct: bool
    unanswered: bool


class KnowledgeMastery(BaseModel):
    name: str
    status: str
    total: int
    correct: int
    score: Optional[float]
    attempt_id: Optional[str] = None
    last_submitted_at: Optional[datetime] = None
    evidence: list[MasteryEvidence]


class MasteryOut(BaseModel):
    exam_id: int
    points: list[KnowledgeMastery]
    note: str = "按最近一次覆盖该知识点的已交卷自测计算，正确率达到 80% 标记已掌握；未作答计错，无记录显示未测。仅供复习参考。"


class ExamFocus(BaseModel):
    content: str
    level: str = "must"  # must 必考 / common 常考
    basis: str = ""
    source: str = ""
    frequency: int = 0  # 出现次数 / 年份数（用例 4.7，用于高频排序）
    citations: list[SourceReference] = []


class QuestionTypeStat(BaseModel):
    """常考题型分布（用例 4.7）"""

    type: str  # 选择题 / 填空题 / 计算题 / 证明题 / 应用题 / 简答题 / 综合题
    count: int = 0  # 资料中可识别的题数 / 出现次数
    frequency: float = Field(0, ge=0, le=1)  # 占比 0~1
    basis: str = ""  # 统计依据
    source: str = ""  # 依据来源
    citations: list[SourceReference] = []


class PlanActivity(BaseModel):
    phase: str
    label: str
    minutes: int = Field(ge=0)
    detail: str = ""


class StudyPhase(BaseModel):
    phase: str
    label: str
    percent: int = Field(ge=0, le=100)
    minutes: int = Field(default=0, ge=0)
    detail: str = ""


class StudyStrategy(BaseModel):
    target_band: Optional[ScoreBand] = None
    target_label: str
    learning_status: str
    available_days: int
    daily_minutes: int
    available_minutes: int
    planned_minutes: int = 0
    deferred_minutes: int = 0
    weak_chapters: list[str] = []
    phases: list[StudyPhase]
    notes: list[str] = []


class PlanItem(BaseModel):
    day: int
    date: str  # YYYY-MM-DD
    title: str
    estimated_minutes: int = 60
    priority: int = 2  # 1 高 / 2 中 / 3 低
    detail: str = ""
    activities: list[PlanActivity] = []  # 同一项任务内部拆分，总和等于 estimated_minutes


class QuizItem(BaseModel):
    question: str
    options: list[str] = []
    answer: str
    analysis: str = ""
    knowledge_point: str = ""
    kind: str = ""  # single / multiple / boolean / fill；旧数据自动识别
    accepted_answers: list[str] = []  # 填空题明确列出的等价写法


class AnalysisResult(BaseModel):
    course: str = ""
    summary: str = ""
    knowledge_points: list[KnowledgePoint] = []
    exam_focus: list[ExamFocus] = []
    question_types: list[QuestionTypeStat] = []  # 常考题型分布（用例 4.7）
    review_plan: list[PlanItem] = []
    quiz: list[QuizItem] = []
    strategy: Optional[StudyStrategy] = None  # 旧分析没有此字段，读取时不伪造新结果


class AnalyzeRequest(BaseModel):
    exam_id: int


# ==================== 动态调整计划与权重（用例 4.12） ====================


class ReplanIn(BaseModel):
    apply: bool = False  # false=只预览，true=写回分析结果并重建未完成任务
    fingerprint: Optional[str] = None  # 确认须携带最近一次预览的快照标识


class WeightChange(BaseModel):
    name: str
    old_weight: float
    new_weight: float
    reason: str = ""


class ReplanOut(BaseModel):
    exam_id: int
    days_left: int
    done_tasks: int
    total_tasks: int
    completion_rate: float  # 0~1
    wrong_questions: int  # 错题本中的自测错题数
    weights: list[WeightChange] = []
    plan: list[PlanItem] = []
    applied: bool = False
    task_count: int = 0  # 应用后新建的任务数
    note: str = ""
    fingerprint: str = ""
    scheduling: dict[str, Any] = {}  # 全科安排、每日容量及冲突


class MindmapNode(BaseModel):
    """思维导图节点（用例 4.4）"""

    name: str
    value: Optional[float] = None  # 知识点权重
    level: str = ""  # high / medium / low / must / common
    source: str = ""
    children: list["MindmapNode"] = []


class MemoryCard(BaseModel):
    """记忆卡片（用例 4.4）：正面提示，背面资料依据"""

    id: int
    front: str
    back: str
    hint: str = ""
    knowledge_point: str = ""
    source: str = ""


class MindmapOut(BaseModel):
    exam_id: int
    course: str
    mindmap: MindmapNode
    cards: list[MemoryCard] = []


class AnalysisOut(BaseModel):
    id: int
    exam_id: int
    status: str
    result: AnalysisResult
    created_at: datetime
    scheduling: Optional[dict] = None


class QuizStart(BaseModel):
    analysis_id: int


class QuizSubmit(BaseModel):
    answers: list[str | list[str]] = Field(min_length=1, max_length=50)


# ==================== 任务 ====================


class TaskDetails(BaseModel):
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    location: str = Field(default='', max_length=120)
    difficulty: Literal['easy', 'medium', 'hard'] = 'medium'
    detail: str = Field(default='', max_length=2000)

    @field_validator('start_time', 'end_time', mode='before')
    @classmethod
    def check_time(cls, value):
        return task_time(value)

    @field_serializer('start_time', 'end_time')
    def format_time(self, value):
        return value.strftime('%H:%M') if value is not None else None

    @field_validator('location', 'detail', mode='before')
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class TaskCreate(TaskDetails):
    model_config = ConfigDict(extra='forbid')
    exam_id: int
    title: str = Field(min_length=1, max_length=256)
    plan_date: date
    estimated_minutes: int = Field(default=60, ge=1, le=1440)
    priority: int = Field(default=2, ge=1, le=3)
    repeat_rule: Literal['none', 'daily', 'weekdays', 'weekly'] = 'none'
    repeat_until: Optional[date] = None

    @field_validator('title', mode='before')
    @classmethod
    def trim_title(cls, value):
        return value.strip() if isinstance(value, str) else value


class TaskUpdate(TaskDetails):
    """编辑任务（2.6）：字段均可选，仅更新传入的字段"""

    model_config = ConfigDict(extra='forbid')
    location: Optional[str] = Field(default=None, max_length=120)
    difficulty: Optional[Literal['easy', 'medium', 'hard']] = None
    detail: Optional[str] = Field(default=None, max_length=2000)
    exam_id: Optional[int] = None
    title: Optional[str] = Field(default=None, min_length=1, max_length=256)
    plan_date: Optional[date] = None
    estimated_minutes: Optional[int] = Field(default=None, ge=1, le=1440)
    priority: Optional[int] = Field(default=None, ge=1, le=3)


class TaskOut(TaskDetails):
    model_config = ConfigDict(from_attributes=True)

    id: int
    exam_id: int
    title: str
    plan_date: date
    estimated_minutes: int
    priority: int
    sort_order: int
    is_done: bool
    done_at: Optional[datetime] = None
    source: str
    repeat_rule: str = 'none'
    repeat_until: Optional[date] = None
    repeat_group_id: Optional[str] = None
    move_fingerprint: str = ''


class TaskCreateOut(TaskOut):
    created_count: int = 1
    created_ids: list[int] = []


class TaskPreviewRequest(TaskCreate):
    exclude_task_id: Optional[int] = Field(default=None, ge=1)


class TaskPreviewOut(BaseModel):
    count: int
    total_minutes: int
    items: list[TaskCreate]
    warnings: list[dict[str, Any]] = []
    overlaps: list[dict[str, Any]] = []
    can_save: bool = True
    note: str = '预览不保存；每个重复日期会生成一项任务，可单独打卡和编辑。请核对日期、时段及预算。'


class TaskMoveIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    plan_date: date
    fingerprint: str = Field(pattern='^[0-9a-f]{64}$')
    start_time: Optional[time] = None  # 省略保留原时段；null 清空时段；有值按原分钟数计算结束
    allow_over_budget: bool = False

    @field_validator('start_time', mode='before')
    @classmethod
    def validate_time(cls, value):
        return task_time(value)


class TaskMovePreviewOut(BaseModel):
    candidate: TaskCreate
    overlaps: list[dict[str, Any]]
    can_save: bool
    changed: bool
    budget_exceeded: bool
    existing_minutes: int
    planned_minutes: int
    limit_minutes: int


# ==================== 日程服务（2.7 倒推 / 2.8 冲突检测 / 2.12 ICS 导入） ====================


class ScheduleGenerateRequest(BaseModel):
    """倒推生成备考时间表（2.7）"""

    daily_minutes: int = Field(default=180, ge=30, le=720, description="每日可用于该科的时间上限")
    start_date: Optional[date] = None  # 不传则从明天开始（考试日早于明天时取考试日前一天）


class ScheduleGenerateOut(BaseModel):
    created: int  # 新建任务数
    total_minutes: int  # 估算的该科总复习时长
    start_date: str
    end_date: str
    conflicts: list[dict[str, Any]] = []  # 与现有日程冲突的日期（当天总时长超上限）


class ConflictCheckRequest(BaseModel):
    """任务冲突检测（2.8）：保存前预检，前端超限时弹提醒"""

    plan_date: date
    estimated_minutes: int = Field(ge=1, le=1440)
    exclude_task_id: Optional[int] = Field(default=None, ge=1)
    daily_limit_minutes: Optional[int] = Field(default=None, ge=30, le=1440)
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    exam_id: Optional[int] = None
    title: str = Field(default='待安排任务', max_length=256)

    @field_validator('start_time', 'end_time', mode='before')
    @classmethod
    def validate_time(cls, value):
        return task_time(value)


class ConflictCheckOut(BaseModel):
    conflict: bool
    date: str
    existing_minutes: int  # 当天已有任务总时长
    planned_minutes: int  # 当天已有 + 新增
    limit_minutes: int
    budget_exceeded: bool = False
    overlaps: list[dict[str, Any]] = []


class IcsImportResult(BaseModel):
    imported: int  # 成功导入任务数
    skipped: int  # 跳过数（无标题/结束早于开始等）
    conflicts: list[dict[str, Any]] = []  # 合并前冲突检测：当天超上限的日期
    already_imported: bool = False


class IcsImportPreview(IcsImportResult):
    count: int
    events: list[dict[str, Any]]
    daily_limit_minutes: int
    preview_token: str
    note: str


class IcsImportConfirm(BaseModel):
    preview_token: str = Field(min_length=1, max_length=2000000)


# ==================== 首页 / 统计 ====================


class ExamDashboard(BaseModel):
    id: int
    subject: str
    exam_date: date
    days_left: int
    location: str
    duration_minutes: int  # 考试时间线展示时长
    total_tasks: int
    done_tasks: int
    progress: float  # 0~1


class DashboardOut(BaseModel):
    exams: list[ExamDashboard]
    today_tasks: list[TaskOut]
    overall: dict[str, Any]


class DailyStat(BaseModel):
    date: str
    total: int
    done: int


class StatsOut(BaseModel):
    exam_id: int
    subject: str
    days_left: int
    total_tasks: int
    done_tasks: int
    rate: float
    by_date: list[DailyStat]
    knowledge_points: list[dict[str, Any]]


# ===================== 特色功能（模块 7）=====================
class PressureOut(BaseModel):
    score: float        # 0~100
    level: str          # 轻松 / 适中 / 偏压 / 高压
    suggestion: str
    breakdown: dict[str, float]
    need_emergency: bool # score >= 60，前端据此提示救急模式


class MoodSubmit(BaseModel):
    mood_score: int = Field(ge=1, le=5)  # 情绪自评 1~5
    note: str = ""


class MoodResult(BaseModel):
    record_date: date
    mood_score: int
    emotion_item: float     # 情绪项
    completion_item: float  # 完成项
    pressure_item: float    # 压力项
    streak_item: float      # 达标项
    composite_score: float  # 情绪综合评分 0~5
    suggestion: str         # 复习节奏建议
    need_relief: bool       # <2.5，前端显示减负入口（用例 7.7）


class EmergencyItem(BaseModel):
    content: str            # 考点 / 知识点内容
    kind: str               # 考点 / 知识点
    level: str = ""         # must / common / high / medium / low
    weight: float | None = None  # 知识点权重，考点为 null
    source: str = ""        # 依据来源
    basis: str = ""         # 推荐依据说明


class EmergencyOut(BaseModel):
    exam_id: int
    subject: str
    exam_date: date
    days_left: int
    items: list[EmergencyItem] = []
    note: str = ""          # 无分析等提示信息


class ReviewItem(BaseModel):
    name: str               # 知识点名称
    weight: float           # 权重 0~1
    importance: str = "medium"  # high / medium / low
    suggest_hours: float = 0  # 兼容历史小时值，新分析优先显示精确分钟
    suggest_minutes: Optional[int] = None
    source: str = ""        # 依据来源
    basis: str = ""         # 推荐依据说明


class ReviewOut(BaseModel):
    exam_id: int
    subject: str
    exam_date: date
    days_left: int
    items: list[ReviewItem] = []
    note: str = ""


class Top3Item(BaseModel):
    task_id: int
    title: str
    subject: str = ""
    plan_date: date
    priority: int
    estimated_minutes: int
    score: float            # 综合打分，用于排序
    reason: str = ""        # 为什么置顶（优先级 / 逾期 / 考试临近）


class Top3Out(BaseModel):
    items: list[Top3Item] = []
    pressure: float = 0.0   # 当前压力指数，打分的一项
    note: str = ""


class TimeSlot(BaseModel):
    name: str               # 早晨 / 上午 / 下午 / 晚上
    start: str              # HH:MM
    end: str                # HH:MM
    minutes: int            # 该时段建议复习分钟数
    focus: str = ""         # 建议内容方向
    history_minutes: int = 0
    study_days: int = 0
    reason: str = ""


class TimeSlotOut(BaseModel):
    daily_hours: float              # 全科共享预算折算小时；保留旧响应字段
    learning_status: str | None = None  # weak / medium / good
    slots: list[TimeSlot] = []
    note: str = ""
    daily_minutes: int
    mode: str
    scope: str
    exam_id: int | None = None
    window_start: str
    window_end: str
    timezone: str
    session_count: int
    study_days: int
    history_minutes: int
    checkin_count: int
    ignored_sessions: int
    recommended_minutes: int
    unallocated_minutes: int


class ReliefMove(BaseModel):
    task_id: int
    title: str
    from_date: date
    to_date: date
    minutes: int
    from_start: str | None = None
    from_end: str | None = None
    to_start: str | None = None
    to_end: str | None = None


class ReliefRetained(BaseModel):
    task_id: int
    title: str
    minutes: int
    start_time: str | None = None
    end_time: str | None = None


class ReliefConflict(BaseModel):
    task_id: int
    title: str
    reason: str = ""


class ReliefPlan(BaseModel):
    option: str             # lighten 减轻当日 / halfday 暂停半天
    daily_hours: float
    today_capacity: int     # 重排后今日可用分钟数
    moves: list[ReliefMove] = []
    conflicts: list[ReliefConflict] = []
    summary: str = ""
    half: str | None = None
    date: str
    daily_minutes: int
    rest_start: str | None = None
    rest_end: str | None = None
    completed_minutes: int
    today_pending_minutes: int
    retained: list[ReliefRetained] = []
    note: str
    fingerprint: str
    preview_at: datetime


class ReliefApply(BaseModel):
    option: Literal['lighten', 'halfday'] = 'lighten'
    half: Literal['morning', 'afternoon'] = 'afternoon'
    fingerprint: str = ''
    preview_at: datetime | None = None


# ===================== 管理端（模块 8）=====================
class CourseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    code: str = ""
    teacher: str = ""
    credit: float = 0.0
    term: str = ""
    note: str = ""


class CourseUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    teacher: Optional[str] = None
    credit: Optional[float] = None
    term: Optional[str] = None
    note: Optional[str] = None


class CourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
    teacher: str
    credit: float
    term: str
    note: str
    created_at: datetime


class AdminUserOut(BaseModel):
    id: int
    username: str
    nickname: str
    student_no: str
    major: str
    grade: str
    is_admin: bool
    is_banned: bool
    exam_count: int = 0
    material_count: int = 0
    created_at: datetime


class AdminMaterialOut(BaseModel):
    id: int
    user_id: int
    username: str
    title: str
    source_type: str
    file_type: str
    parse_status: str
    created_at: datetime


# ==================== 学习统计总览（FMZH-SRS-5.2.0，张诗琦） ====================


class SubjectStat(BaseModel):
    exam_id: Optional[int] = None  # None 表示未指定科目的自由专注
    subject: str
    archived: bool = False
    minutes: int  # 番茄钟聚合时长（受 days 窗口限制）
    total_tasks: int  # 全量课程进度（与首页口径一致）
    done_tasks: int
    rate: float
    exam_date: Optional[date] = None
    days_left: Optional[int] = None


class DayStat(BaseModel):
    date: str  # YYYY-MM-DD
    minutes: int  # 当日专注时长
    total: int  # 当日计划任务数
    done: int
    rate: float


class StatsOverviewOut(BaseModel):
    range_days: int
    start_date: str
    end_date: str
    total_minutes: int  # 窗口内总专注时长
    total_tasks: int
    done_tasks: int
    rate: float
    subjects: list[SubjectStat]
    days: list[DayStat]


# ==================== 番茄钟（FMZH-SRS-2.10.0） ====================


class FocusSessionCreate(BaseModel):
    exam_id: Optional[int] = None  # 为空表示未指定科目的自由专注
    duration_minutes: int = Field(default=25, ge=1, le=180)
    start_time: Optional[datetime] = None  # 不传则按 end_time - duration 推算
    end_time: Optional[datetime] = None  # 不传则取服务器当前时间


class FocusSessionOut(BaseModel):
    id: int
    exam_id: Optional[int] = None
    subject: str  # 由 exam_id 关联得到；无科目时为空串
    archived: bool = False
    duration_minutes: int
    start_time: datetime
    end_time: datetime
    created_at: datetime


class FocusExamStat(BaseModel):
    exam_id: Optional[int] = None
    subject: str
    archived: bool = False
    minutes: int


class FocusTodayOut(BaseModel):
    date: str
    total_minutes: int
    goal_minutes: int  # 0 表示当日未设定目标
    achieved: bool
    session_count: int
    by_exam: list[FocusExamStat]


class FocusGoalUpdate(BaseModel):
    target_minutes: int = Field(ge=0, le=1440)
    goal_date: Optional[date] = None  # 不传则默认今天


class FocusGoalOut(BaseModel):
    goal_date: date
    target_minutes: int


# ==================== 备考周报（FMZH-SRS-5.3.0） ====================


class WeeklyReportRequest(BaseModel):
    """按需生成周报：不传 week_start 时统计最近 7 天（含今天）"""

    week_start: Optional[date] = None  # 起始日；统计 [week_start, week_start+6] 且不超过今天


class WeeklySubjectOut(BaseModel):
    exam_id: Optional[int] = None  # None 表示「未指定科目」的自由专注
    subject: str
    archived: bool = False
    minutes: int
    total_tasks: int
    done_tasks: int
    rate: float
    exam_date: Optional[date] = None
    days_left: Optional[int] = None
    mastery: Optional[int] = Field(default=None, ge=0, le=100)  # 大模型评测的掌握度 0~100
    level: str = ""  # 优秀 / 良好 / 一般 / 薄弱
    comment: str = ""
    suggestions: list[str] = []


class WeeklyDayOut(BaseModel):
    date: str
    minutes: int
    total: int
    done: int
    rate: float


class WeeklyReportOut(BaseModel):
    week_start: str
    week_end: str
    generated_at: datetime
    total_minutes: int
    total_tasks: int
    done_tasks: int
    rate: float
    active_days: int  # 窗口内有专注记录的天数
    overall_mastery: Optional[int] = Field(default=None, ge=0, le=100)
    summary: str = ""
    highlights: list[str] = []
    next_week_advice: list[str] = []
    subjects: list[WeeklySubjectOut] = []
    days: list[WeeklyDayOut] = []
    note: str = ""
