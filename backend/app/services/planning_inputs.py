"""模型调用前后校验规划输入；只保存摘要，不在等待模型期间持有写锁。"""
import hashlib
import json

from ..models.models import Analysis, Exam, Material, UserProfile
from .study_planner import preview


def values(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns} if row else None


def profile_inputs(db, user_id, exam_id):
    exam = db.query(Exam).filter(Exam.id == exam_id, Exam.user_id == user_id).first()
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id, UserProfile.exam_id == exam_id).order_by(UserProfile.id.desc()).first()
    return [values(exam), values(profile)]


def signature(db, user_id, exam_id, *, analysis=False):
    state = profile_inputs(db, user_id, exam_id)
    if analysis:
        materials = db.query(Material).filter(Material.user_id == user_id, Material.exam_id == exam_id).order_by(Material.id).all()
        latest = db.query(Analysis).filter(Analysis.user_id == user_id, Analysis.exam_id == exam_id).order_by(Analysis.id.desc()).first()
        state += [[values(row) for row in materials], values(latest), preview(db, user_id)['fingerprint']]
    return hashlib.sha256(json.dumps(state, default=str, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
