"""数据库表模型（共 21 张表）

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
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Index,
    String,
    Text,
    Time,
    UniqueConstraint,
)

from ..database import Base


class User(Base):
    """用户"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(32), unique=True, index=True, nullable=False)
    hashed_password = Column(String(128), nullable=False)
    auth_key = Column(String(64), nullable=False, default=lambda: uuid4().hex)
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
    text_locations = Column(Text, nullable=False, default="[]")  # 页/段落/行 → 解析文本偏移
    parse_status = Column(String(16), default="done")  # done / failed
    description = Column(String(512), default="")
    tags = Column(String(256), default="")
    # 资料权重（用例 4.2）：上传时按来源层级给默认值，学生可手动调整（0~1）
    weight = Column(Float, default=0.5)
    created_at = Column(DateTime, default=datetime.now)

    @property
    def default_weight(self) -> float:
        """当前来源类型对应的默认权重，供前端「恢复默认」使用"""
        from ..services.material_weight import default_weight_for

        return default_weight_for(self.source_type)

    @property
    def weight_level(self) -> str:
        """权重档位（用例 3.2）：高 / 中 / 低"""
        from ..services.material_weight import weight_level_for

        return weight_level_for(self.weight if self.weight is not None else self.default_weight)


class UserProfile(Base):
    """AI 用户画像（第一次大模型调用的产物）"""

    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    exam_id = Column(Integer, ForeignKey("exams.id"), index=True, nullable=False)
    raw_text = Column(Text, default="")  # 用户原始自然语言描述（含补全内容）
    target = Column(String(16), nullable=True)  # pass / medium / high
    target_band = Column(String(8), nullable=True)  # 川大本科目标成绩区间 D 至 A
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
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)
    location = Column(String(120), nullable=False, default='')
    difficulty = Column(String(16), nullable=False, default='medium')
    detail = Column(Text, nullable=False, default='')
    repeat_rule = Column(String(16), nullable=False, default='none')
    repeat_until = Column(Date, nullable=True)
    repeat_group_id = Column(String(32), nullable=True, index=True)
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
    __table_args__ = (Index("uq_collections_user_question", "user_id", "question_key", unique=True),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    item_type = Column(String(16), nullable=False)  # material=资料 / question=题目
    material_id = Column(Integer, ForeignKey("materials.id"), nullable=True)  # 收藏资料时指向资料
    title = Column(String(256), default="")  # 展示用：资料标题或题干
    content = Column(Text, default="")  # 题目详情 JSON（选项/答案/解析/知识点）
    question_key = Column(String(64), nullable=True)
    source = Column(String(16), default="manual")  # manual=学生手动收藏 / quiz=自测答错自动入本
    created_at = Column(DateTime, default=datetime.now)


class QuizAttempt(Base):
    """一次自测的服务端题目快照、作答与判分；提交后不可改写。"""

    __tablename__ = "quiz_attempts"
    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    exam_id = Column(Integer, ForeignKey("exams.id"), index=True, nullable=False)
    analysis_id = Column(Integer, ForeignKey("analyses.id"), index=True, nullable=False)
    subject = Column(String(64), nullable=False)
    questions_json = Column(Text, nullable=False)
    status = Column(String(16), nullable=False, default="active")
    answers_json = Column(Text, nullable=True)
    result_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    submitted_at = Column(DateTime, nullable=True)


class QaConversation(Base):
    """资料问答会话（用例 4.5）：一个会话对应一个科目的多轮问答"""

    __tablename__ = "qa_conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    exam_id = Column(Integer, ForeignKey("exams.id"), index=True, nullable=False)
    title = Column(String(128), default="")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class QaMessage(Base):
    """资料问答消息（用例 4.5）：role=user / assistant，按 id 顺序构成多轮对话"""

    __tablename__ = "qa_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(
        Integer, ForeignKey("qa_conversations.id"), index=True, nullable=False
    )
    role = Column(String(16), nullable=False)  # user / assistant
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.now)


class FocusSession(Base):
    """番茄钟记录：一次专注计时的结果，为学习时长统计的唯一依据（见 FMZH-SRS-2.10.0）

    时长按 exam_id 归入对应科目；exam_id 为空表示未指定科目的自由专注。
    """

    __tablename__ = "focus_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    exam_id = Column(Integer, ForeignKey("exams.id"), index=True, nullable=True)
    subject_snapshot = Column(String(64), nullable=False, default="")
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


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    enabled = Column(Boolean, nullable=False, default=True)
    exam_enabled = Column(Boolean, nullable=False, default=True)
    task_enabled = Column(Boolean, nullable=False, default=True)


class Reminder(Base):
    """按事项当前日期 + 时刻 - 提前量计算提醒，任务改期后自动跟随。"""
    __tablename__ = "reminders"
    __table_args__ = (UniqueConstraint("user_id", "target_type", "target_id", name="uq_reminder_target"),)
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    target_type = Column(String(8), nullable=False)
    target_id = Column(Integer, nullable=False)
    target_created_at = Column(DateTime, nullable=False)  # 防止删除后的事项 ID 重用继承设置
    enabled = Column(Boolean, nullable=False, default=True)
    event_time = Column(String(5), nullable=False, default="09:00")
    advance_minutes = Column(Integer, nullable=False, default=0)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("user_id", "occurrence_key", name="uq_notification_occurrence"),)
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    occurrence_key = Column(String(64), nullable=False)
    target_type = Column(String(8), nullable=False)
    target_id = Column(Integer, nullable=False)
    target_created_at = Column(DateTime, nullable=False)
    title = Column(String(50), nullable=False)
    content = Column(String(200), nullable=False)
    due_at = Column(DateTime, nullable=False)  # UTC
    created_at = Column(DateTime, nullable=False)  # UTC，实际打开页面生成的时间
    is_read = Column(Boolean, nullable=False, default=False)
    deleted_at = Column(DateTime, nullable=True)  # 保留去重凭据，删除后刷新不会再生成


class FileCleanupJob(Base):
    """数据库删除提交后重试文件清理，账号删除后也能继续处理。"""

    __tablename__ = "file_cleanup_jobs"
    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex)
    file_path = Column(String(512), unique=True, nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(String(80), nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class IcsImportReceipt(Base):
    """只在确认导入时写入的幂等凭据；预览不写数据库。"""

    __tablename__ = "ics_import_receipts"
    id = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    exam_id = Column(Integer, ForeignKey("exams.id"), index=True, nullable=False)
    imported = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class OperationLog(Base):
    """不可通过业务接口编辑；保留操作者快照，不依赖已注销账号。"""

    __tablename__ = "operation_logs"
    id = Column(Integer, primary_key=True)
    actor_id = Column(Integer, nullable=True, index=True)
    actor_name = Column(String(64), nullable=False, default="")
    action = Column(String(48), nullable=False, index=True)
    target_id = Column(String(64), nullable=False, default="")
    method = Column(String(8), nullable=False)
    path = Column(String(160), nullable=False)
    status_code = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, index=True)
