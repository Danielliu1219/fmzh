"""数据库表模型（共 6 张表）

users ──< exams ──< materials
  │         │
  │         └──< user_profiles ──< analyses
  │                                 │
  └────────────< tasks ─────────────┘
"""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)

from ..database import Base


class User(Base):
    """用户"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(32), unique=True, index=True, nullable=False)
    hashed_password = Column(String(128), nullable=False)
    nickname = Column(String(64), default="")
    student_no = Column(String(32), default="")
    major = Column(String(64), default="")
    grade = Column(String(16), default="")
    created_at = Column(DateTime, default=datetime.now)


class Exam(Base):
    """考试安排"""

    __tablename__ = "exams"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    subject = Column(String(64), nullable=False)
    exam_date = Column(Date, nullable=False)
    location = Column(String(128), default="")
    duration_minutes = Column(Integer, default=120)
    note = Column(String(256), default="")
    created_at = Column(DateTime, default=datetime.now)


class Material(Base):
    """复习资料：上传文件 + 解析出的纯文本"""

    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    exam_id = Column(Integer, ForeignKey("exams.id"), index=True, nullable=True)
    title = Column(String(128), nullable=False)
    source_type = Column(String(32), default="其他")  # 历年题/老师重点/课堂笔记/作业/练习题/其他
    file_path = Column(String(512), nullable=False)
    file_type = Column(String(16), nullable=False)  # txt / pdf / docx
    text_content = Column(Text, default="")  # 解析出的纯文本，AI 分析的数据源
    parse_status = Column(String(16), default="done")  # done / failed
    description = Column(String(512), default="")
    tags = Column(String(256), default="")
    created_at = Column(DateTime, default=datetime.now)


class UserProfile(Base):
    """AI 用户画像（第一次大模型调用的产物）"""

    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    exam_id = Column(Integer, ForeignKey("exams.id"), index=True, nullable=False)
    raw_text = Column(Text, default="")  # 用户原始自然语言描述（含补全内容）
    target = Column(String(16), nullable=True)  # pass / medium / high
    learning_status = Column(String(16), nullable=True)  # weak / medium / good
    available_days = Column(Integer, nullable=True)
    daily_hours = Column(Float, nullable=True)
    weak_chapters = Column(Text, default="[]")  # JSON 数组
    output_need = Column(Text, default="[]")  # JSON 数组
    is_complete = Column(Boolean, default=False)
    missing_fields = Column(Text, default="[]")  # JSON 数组
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class Analysis(Base):
    """AI 复习分析结果（第二次大模型调用的产物，result_json 为固定格式 JSON）"""

    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    exam_id = Column(Integer, ForeignKey("exams.id"), index=True, nullable=False)
    profile_id = Column(Integer, ForeignKey("user_profiles.id"), nullable=False)
    result_json = Column(Text, nullable=False)
    status = Column(String(16), default="success")  # success / failed
    error_msg = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now)


class Task(Base):
    """每日复习任务：由 AI 复习计划自动生成（source=ai），也可手动添加（source=manual）"""

    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    exam_id = Column(Integer, ForeignKey("exams.id"), index=True, nullable=False)
    analysis_id = Column(Integer, ForeignKey("analyses.id"), nullable=True)
    title = Column(String(256), nullable=False)
    plan_date = Column(Date, index=True, nullable=False)
    estimated_minutes = Column(Integer, default=60)
    priority = Column(Integer, default=2)  # 1 高 / 2 中 / 3 低
    sort_order = Column(Integer, default=0)
    is_done = Column(Boolean, default=False)
    done_at = Column(DateTime, nullable=True)
    source = Column(String(16), default="ai")  # ai / manual
    created_at = Column(DateTime, default=datetime.now)
