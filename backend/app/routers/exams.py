"""考试接口：增删改查（均限定为当前登录用户自己的数据）"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.models import Exam, User
from ..schemas.schemas import ExamCreate, ExamOut, ExamUpdate
from ..utils.security import get_current_user

router = APIRouter()


def _get_own_exam(db: Session, user: User, exam_id: int) -> Exam:
    exam = db.query(Exam).filter(Exam.id == exam_id, Exam.user_id == user.id).first()
    if exam is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="考试不存在")
    return exam


@router.get("", response_model=list[ExamOut], summary="我的考试列表（按考试时间排序）")
def list_exams(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(Exam)
        .filter(Exam.user_id == user.id)
        .order_by(Exam.exam_date, Exam.id)
        .all()
    )


@router.post("", response_model=ExamOut, summary="录入考试")
def create_exam(
    payload: ExamCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exam = Exam(user_id=user.id, **payload.model_dump())
    db.add(exam)
    db.commit()
    db.refresh(exam)
    return exam


@router.put("/{exam_id}", response_model=ExamOut, summary="修改考试")
def update_exam(
    exam_id: int,
    payload: ExamUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exam = _get_own_exam(db, user, exam_id)
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(exam, field, value)
    db.commit()
    db.refresh(exam)
    return exam


@router.delete("/{exam_id}", summary="删除考试")
def delete_exam(
    exam_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exam = _get_own_exam(db, user, exam_id)
    db.delete(exam)
    db.commit()
    return {"ok": True}
