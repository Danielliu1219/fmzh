"""数据库表模型（共 12 张表）

users ──< exams ──< materials ──< collections
  │         │
  │         └──< user_profiles ──< analyses
  │                                 │
  ├────────────< tasks ─────────────┘
  │
  ├──< focus_sessions   番茄钟记录（学习时长统计唯一依据）
  └──< focus_goals      每日学习时长目标
另含 mood_records（情绪记录，模块 7.6）与 courses（课程/科目基础数据，模块 8.1）。
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
    UniqueConstraint,
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
    class_name = Column(String(32), default="")  # 班级（FMZH-USR-0005）
    avatar = Column(String(16), default="")  # 头像色值（预设色板之一），空为默认墨色
    is_admin = Column(Boolean, default=False)  # 管理端 8.x：管理员身份
    is_banned = Column(Boolean, default=False)  # 管理端 8.2：异常账号封禁
    failed_attempts = Column(Integer, default=0)  # 连续登录失败次数（成功登录后清零）
    locked_until = Column(DateTime, nullable=True)  # 锁定截止时间；空表示未锁定
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
    color = Column(String(16), default="")  # 科目颜色标签（2.11，全站统一），空则按科目名取默认色
    created_at = Column(DateTime, default=datetime.now)


class Material(Base):
    """复习资料：上传文件 + 解析出的纯文本"""

    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    exam_id = Column(Integer, ForeignKey("exams.id"), index=True, nullable=True)
    title = Column(String(128), nullable=False)
    source_type = Column(String(32), default="其他")  # 历年题/老师重点/平时作业/课堂笔记/教材章节/实验报告/练习题/其他
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


class MoodRecord(Base):
    """每日情绪记录（模块 7.6）：每个用户每天一条，情绪自评 1~5"""

    __tablename__ = "mood_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    record_date = Column(Date, index=True, nullable=False)  # 记录当天
    mood_score = Column(Integer, nullable=False)  # 情绪自评 1~5
    note = Column(String(256), default="")
    created_at = Column(DateTime, default=datetime.now)


class Course(Base):
    """课程/科目基础数据（管理端 8.1 维护，全站可参照）"""

    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), nullable=False)  # 课程/科目名称
    code = Column(String(32), default="")  # 课程代码
    teacher = Column(String(64), default="")  # 任课教师
    credit = Column(Float, default=0.0)  # 学分
    term = Column(String(32), default="")  # 开课学期
    note = Column(String(256), default="")
    created_at = Column(DateTime, default=datetime.now)


class Collection(Base):
    """收藏与错题本（用例 3.5）：收藏资料、收藏题目、自测答错的题目共用一个本子"""

    __tablename__ = "collections"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    item_type = Column(String(16), nullable=False)  # material=资料 / question=题目
    material_id = Column(Integer, ForeignKey("materials.id"), nullable=True)  # 收藏资料时指向资料
    title = Column(String(256), default="")  # 展示用：资料标题或题干
    content = Column(Text, default="")  # 题目详情 JSON（选项/答案/解析/知识点）
    source = Column(String(16), default="manual")  # manual=学生手动收藏 / quiz=自测答错自动入本
    created_at = Column(DateTime, default=datetime.now)


class FocusSession(Base):
    """番茄钟记录：一次专注计时的结果，为学习时长统计的唯一依据（见 FMZH-SRS-2.10.0）

    时长按 exam_id 归入对应科目；exam_id 为空表示未指定科目的自由专注。
    """

    __tablename__ = "focus_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    exam_id = Column(Integer, ForeignKey("exams.id"), index=True, nullable=True)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    duration_minutes = Column(Integer, nullable=False)  # 1~180，单个默认 25
    created_at = Column(DateTime, default=datetime.now)


class FocusGoal(Base):
    """每日学习时长目标（当日目标，按天存；0~1440 分钟）"""

    __tablename__ = "focus_goals"
    __table_args__ = (UniqueConstraint("user_id", "goal_date", name="uq_focus_goal_user_date"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    goal_date = Column(Date, index=True, nullable=False)
    target_minutes = Column(Integer, default=0)  # 0 表示未设定
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class StudySetting(Base):
    """全科共享的每日时间预算；科目画像仍保存各科目标和基础。"""

    __tablename__ = "study_settings"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    daily_minutes = Column(Integer, nullable=False, default=240)
