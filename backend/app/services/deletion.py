"""关联删除和提交后的文件清理。业务删除失败时不触碰磁盘。"""
import os
import logging
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from ..config import UPLOAD_DIR
from ..models.models import (
    Analysis, Collection, Exam, FileCleanupJob, FocusSession, IcsImportReceipt, Material,
    Notification, QaConversation, QaMessage, QuizAttempt, Reminder, Task, UserProfile,
)


def delete_exam(db: Session, user_id: int, exam_id: int):
    try:
        from .task_conflicts import lock_schedule
        lock_schedule(db, user_id)
        # 先取得写锁，再读取关联集合，防并发创建子记录漏删。
        locked = db.query(Exam).filter(Exam.id == exam_id, Exam.user_id == user_id).update(
            {Exam.id: exam_id}, synchronize_session=False)
        if not locked:
            raise HTTPException(404, "考试不存在")
        exam = db.get(Exam, exam_id, populate_existing=True)
        task_ids = db.query(Task.id).filter(Task.user_id == user_id, Task.exam_id == exam_id)
        for model in (Reminder, Notification):
            db.query(model).filter(model.user_id == user_id, (
                ((model.target_type == "exam") & (model.target_id == exam_id))
                | ((model.target_type == "task") & model.target_id.in_(task_ids))
            )).delete(synchronize_session=False)
        conversations = db.query(QaConversation.id).filter(
            QaConversation.user_id == user_id, QaConversation.exam_id == exam_id)
        db.query(QaMessage).filter(QaMessage.conversation_id.in_(conversations)).delete(synchronize_session=False)
        db.query(QaConversation).filter(QaConversation.user_id == user_id, QaConversation.exam_id == exam_id).delete(synchronize_session=False)
        for model in (IcsImportReceipt, QuizAttempt, Task, Analysis, UserProfile):
            db.query(model).filter(model.user_id == user_id, model.exam_id == exam_id).delete(synchronize_session=False)
        db.query(Material).filter(Material.user_id == user_id, Material.exam_id == exam_id).update(
            {Material.exam_id: None}, synchronize_session=False)
        db.query(FocusSession).filter(FocusSession.user_id == user_id, FocusSession.exam_id == exam_id).update(
            {FocusSession.exam_id: None, FocusSession.subject_snapshot: exam.subject}, synchronize_session=False)
        db.delete(exam)
        db.commit()
    except Exception:
        db.rollback()
        raise


def _key(path: str | Path) -> str:
    return os.path.normcase(str(Path(path).resolve()))


def _upload_path(path: str) -> Path:
    target, root = Path(path).resolve(), UPLOAD_DIR.resolve()
    if target == root or not target.is_relative_to(root) or (target.exists() and not target.is_file()):
        raise HTTPException(409, "上传文件路径异常，请联系管理员处理")
    return target


def _has_reference(db: Session, path: Path, excluding: int | None = None) -> bool:
    query = db.query(Material.file_path)
    if excluding is not None:
        query = query.filter(Material.id != excluding)
    return any(_key(value) == _key(path) for (value,) in query.all())


def retry_file_cleanup(db: Session, limit: int = 20) -> dict:
    completed = 0
    ids = [row[0] for row in db.query(FileCleanupJob.id).order_by(FileCleanupJob.created_at).limit(limit)]
    for job_id in ids:
        try:
            # 写锁覆盖“检查共享引用 → unlink”，避免多个重试并行处理同一文件。
            if not db.query(FileCleanupJob).filter(FileCleanupJob.id == job_id).update(
                {FileCleanupJob.attempts: FileCleanupJob.attempts + 1}, synchronize_session=False):
                db.rollback()
                continue
            job = db.get(FileCleanupJob, job_id, populate_existing=True)
            try:
                path = _upload_path(job.file_path)
                if not _has_reference(db, path):
                    path.unlink(missing_ok=True)
            except (OSError, HTTPException) as exc:
                job.last_error = type(exc).__name__
            else:
                db.delete(job)
                completed += 1
            db.commit()
        except Exception:
            db.rollback()
            raise
    return {"completed": completed, "pending": db.query(FileCleanupJob).count()}


def delete_material(db: Session, material_id: int, owner_id: int | None = None) -> dict:
    try:
        query = db.query(Material).filter(Material.id == material_id)
        if owner_id is not None:
            query = query.filter(Material.user_id == owner_id)
        if not query.update({Material.id: material_id}, synchronize_session=False):
            raise HTTPException(404, "资料不存在")
        material = db.get(Material, material_id, populate_existing=True)
        path = _upload_path(material.file_path)
        db.query(Collection).filter(Collection.material_id == material_id).delete(synchronize_session=False)
        db.delete(material)
        if not _has_reference(db, path, excluding=material_id):
            if db.query(FileCleanupJob).filter(FileCleanupJob.file_path == str(path)).first() is None:
                db.add(FileCleanupJob(file_path=str(path)))
        db.commit()
    except Exception:
        db.rollback()
        raise
    try:
        retry_file_cleanup(db)
        pending = db.query(FileCleanupJob).filter(FileCleanupJob.file_path == str(path)).first() is not None
    except SQLAlchemyError:
        db.rollback()
        logging.getLogger(__name__).exception('Post-commit file cleanup deferred')
        pending = True
    return {"ok": True, "cleanup_pending": pending}
