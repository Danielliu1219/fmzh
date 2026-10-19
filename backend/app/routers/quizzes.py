"""自测：固定题目快照 → 作答 → 后端判分与错题入本，保存历史。"""
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.models import Analysis, Exam, QuizAttempt, User
from ..schemas.schemas import QuizStart, QuizSubmit
from ..services.mistakes import save_question
from ..services.quizzes import attempt_output, grade_questions, prepare_questions
from ..utils.security import get_current_user

router = APIRouter()


def owned_attempt(db, user, attempt_id):
    attempt = db.query(QuizAttempt).filter(QuizAttempt.id == attempt_id, QuizAttempt.user_id == user.id).first()
    if attempt is None:
        raise HTTPException(404, "自测记录不存在")
    return attempt


@router.get("")
def history(analysis_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    own = db.query(Analysis).filter(Analysis.id == analysis_id, Analysis.user_id == user.id).first()
    if own is None:
        raise HTTPException(404, "分析不存在")
    attempts = db.query(QuizAttempt).filter(QuizAttempt.user_id == user.id, QuizAttempt.analysis_id == analysis_id).order_by(QuizAttempt.created_at.desc()).limit(20).all()
    return [dict(id=a.id, status=a.status, created_at=a.created_at, score=json.loads(a.result_json)["score"] if a.result_json else None) for a in attempts]


@router.post("", status_code=201)
def start(payload: QuizStart, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    analysis = db.query(Analysis).filter(Analysis.id == payload.analysis_id, Analysis.user_id == user.id, Analysis.status == "success").first()
    exam = db.query(Exam).filter(Exam.id == analysis.exam_id, Exam.user_id == user.id).first() if analysis else None
    if analysis is None or exam is None:
        raise HTTPException(404, "分析或对应考试不存在")
    try:
        questions = prepare_questions(json.loads(analysis.result_json).get("quiz"))
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(422, f"自测题暂不可用：{exc}")
    attempt = QuizAttempt(user_id=user.id, exam_id=exam.id, analysis_id=analysis.id, subject=exam.subject, questions_json=json.dumps(questions, ensure_ascii=False))
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt_output(attempt)


@router.get("/{attempt_id}")
def detail(attempt_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return attempt_output(owned_attempt(db, user, attempt_id))


@router.post("/{attempt_id}/submit")
def submit(attempt_id: str, payload: QuizSubmit, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    attempt = owned_attempt(db, user, attempt_id)
    answers, result = grade_questions(json.loads(attempt.questions_json), payload.answers)
    answers_json = json.dumps(answers, ensure_ascii=False)
    if attempt.status == "submitted":
        if attempt.answers_json != answers_json:
            raise HTTPException(409, "此答卷已提交；请重新开始一轮自测")
        return attempt_output(attempt)
    claimed = db.query(QuizAttempt).filter(QuizAttempt.id == attempt.id, QuizAttempt.user_id == user.id, QuizAttempt.status == "active").update({QuizAttempt.status: "submitted"}, synchronize_session=False)
    if claimed != 1:
        db.rollback()
        db.refresh(attempt)
        if attempt.answers_json == answers_json:
            return attempt_output(attempt)
        raise HTTPException(409, "此答卷已提交；请重新开始一轮自测")
    try:
        for item in result["items"]:
            if not item["correct"]:
                content = json.dumps({**item, "subject": attempt.subject, "exam_id": attempt.exam_id}, ensure_ascii=False)
                collection, added = save_question(db, user.id, item["question"], content)
                item["collection_id"] = collection.id
                result["mistakes_added"] += int(added)
        attempt.status = "submitted"
        attempt.answers_json = answers_json
        attempt.result_json = json.dumps(result, ensure_ascii=False)
        attempt.submitted_at = datetime.now()
        db.commit()
    except Exception:
        db.rollback()
        raise
    return attempt_output(attempt)
