"""按知识点最近一次已交卷自测统计；草稿不计分，不跨用户或科目取证。"""
import json

from ..models.models import QuizAttempt
from .quizzes import clean_text
from .mistakes import normalized_title


def knowledge_mastery(db, user_id: int, exam_id: int, names: list[str]) -> list[dict]:
    attempts = db.query(QuizAttempt).filter(
        QuizAttempt.user_id == user_id, QuizAttempt.exam_id == exam_id,
        QuizAttempt.status == 'submitted', QuizAttempt.submitted_at.is_not(None),
    ).order_by(QuizAttempt.submitted_at.desc(), QuizAttempt.created_at.desc(), QuizAttempt.id.desc()).all()
    latest = {}
    for attempt in attempts:
        try:
            items = json.loads(attempt.result_json or '{}').get('items', [])
        except (ValueError, AttributeError):
            continue
        grouped = {}
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get('correct'), bool):
                continue
            name = clean_text(str(item.get('knowledge_point') or '')).casefold()
            question = str(item.get('question') or '').strip()
            if name and question:
                grouped.setdefault(name, {})[normalized_title(question)] = dict(
                    question=question, correct=item['correct'], unanswered=bool(item.get('unanswered')))
        for name, questions in grouped.items():
            if name not in latest:
                latest[name] = dict(attempt_id=attempt.id, last_submitted_at=attempt.submitted_at,
                                    evidence=list(questions.values()))
    points = []
    for name in names:
        evidence = latest.get(clean_text(name).casefold(), {})
        items = evidence.get('evidence', [])
        total, correct = len(items), sum(item['correct'] for item in items)
        score = round(correct / total * 100, 1) if total else None
        points.append(dict(name=name, status='untested' if not total else 'mastered' if score >= 80 else 'weak',
                           total=total, correct=correct, score=score, attempt_id=evidence.get('attempt_id'),
                           last_submitted_at=evidence.get('last_submitted_at'), evidence=items))
    return points
