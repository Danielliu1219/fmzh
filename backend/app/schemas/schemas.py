"""Pydantic 请求/响应模型：前后端接口契约

字段含义、枚举取值与 docs/接口文档.md 保持一致。
"""
from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

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
    created_at: datetime
    snippet: str = ""  # 全文搜索命中片段（用例 3.4），仅带 keyword 查询时返回


class MaterialDetailOut(MaterialOut):
    text_preview: str = ""  # 解析文本前 1000 字


class MaterialUpdate(BaseModel):
    """资料编辑 / 移动分类（用例 3.3）：字段均可选，只更新请求里出现的字段"""

    title: Optional[str] = None
    exam_id: Optional[int] = None  # 传 null 表示移出科目（回到「未归类」）
    source_type: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[str] = None


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


class ProfileOut(BaseModel):
    exam_id: int
    raw_text: str
    target: Optional[str] = None  # pass / medium / high
    learning_status: Optional[str] = None  # weak / medium / good
    available_days: Optional[int] = None
    daily_hours: Optional[float] = None
    weak_chapters: list[str] = []
    output_need: list[str] = []
    is_complete: bool = False
    missing_fields: list[str] = []


# ==================== AI 分析（第二次调用） ====================


class KnowledgePoint(BaseModel):
    name: str
    weight: float = Field(ge=0, le=1)
    importance: str = "medium"  # high / medium / low
    recommend_reason: str = ""
    source: str = ""  # 推荐依据来自哪类资料
    suggest_hours: int = 0


class ExamFocus(BaseModel):
    content: str
    level: str = "must"  # must 必考 / common 常考
    basis: str = ""
    source: str = ""


class PlanItem(BaseModel):
    day: int
    date: str  # YYYY-MM-DD
    title: str
    estimated_minutes: int = 60
    priority: int = 2  # 1 高 / 2 中 / 3 低
    detail: str = ""


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
    review_plan: list[PlanItem] = []
    quiz: list[QuizItem] = []


class AnalyzeRequest(BaseModel):
    exam_id: int


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


class TaskCreate(BaseModel):
    exam_id: int
    title: str = Field(min_length=1, max_length=256)
    plan_date: date
    estimated_minutes: int = 60
    priority: int = Field(default=2, ge=1, le=3)


class TaskUpdate(BaseModel):
    """编辑任务（2.6）：字段均可选，仅更新传入的字段"""

    exam_id: Optional[int] = None
    title: Optional[str] = Field(default=None, min_length=1, max_length=256)
    plan_date: Optional[date] = None
    estimated_minutes: Optional[int] = Field(default=None, ge=1, le=1440)
    priority: Optional[int] = Field(default=None, ge=1, le=3)


class TaskOut(BaseModel):
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
    exclude_task_id: Optional[int] = None  # 编辑场景排除自身
    daily_limit_minutes: int = Field(default=480, ge=30, le=1440)


class ConflictCheckOut(BaseModel):
    conflict: bool
    date: str
    existing_minutes: int  # 当天已有任务总时长
    planned_minutes: int  # 当天已有 + 新增
    limit_minutes: int


class IcsImportResult(BaseModel):
    imported: int  # 成功导入任务数
    skipped: int  # 跳过数（无标题/结束早于开始等）
    conflicts: list[dict[str, Any]] = []  # 合并前冲突检测：当天超上限的日期


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
    suggest_hours: int = 0  # 建议复习时长（小时）
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


class TimeSlotOut(BaseModel):
    daily_hours: float              # 画像里的每日可用时长
    learning_status: str | None = None  # weak / medium / good
    slots: list[TimeSlot] = []
    note: str = ""


class ReliefMove(BaseModel):
    task_id: int
    title: str
    from_date: date
    to_date: date
    minutes: int


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


class ReliefApply(BaseModel):
    option: str = "lighten"  # lighten / halfday


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
    duration_minutes: int
    start_time: datetime
    end_time: datetime
    created_at: datetime


class FocusExamStat(BaseModel):
    exam_id: Optional[int] = None
    subject: str
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
