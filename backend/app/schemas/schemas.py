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


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    nickname: str
    student_no: str
    major: str
    grade: str
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ==================== 考试 ====================


class ExamCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=64)
    exam_date: date
    location: str = ""
    duration_minutes: int = 120
    note: str = ""


class ExamUpdate(BaseModel):
    subject: Optional[str] = None
    exam_date: Optional[date] = None
    location: Optional[str] = None
    duration_minutes: Optional[int] = None
    note: Optional[str] = None


class ExamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subject: str
    exam_date: date
    location: str
    duration_minutes: int
    note: str
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


class MaterialDetailOut(MaterialOut):
    text_preview: str = ""  # 解析文本前 1000 字


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


# ==================== 任务 ====================


class TaskCreate(BaseModel):
    exam_id: int
    title: str = Field(min_length=1, max_length=256)
    plan_date: date
    estimated_minutes: int = 60
    priority: int = Field(default=2, ge=1, le=3)


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


# ==================== 首页 / 统计 ====================


class ExamDashboard(BaseModel):
    id: int
    subject: str
    exam_date: date
    days_left: int
    location: str
    duration_minutes: int  # 考表时间线展示时长
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
