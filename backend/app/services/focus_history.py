"""已删除考试保留科目名和分钟数，不混入自由专注或新的掌握度评测。"""
from collections import defaultdict


def archived_subjects(sessions):
    minutes = defaultdict(int)
    for session in sessions:
        if session.exam_id is None and session.subject_snapshot:
            minutes[session.subject_snapshot] += session.duration_minutes
    return [dict(exam_id=None, subject=name if name == '已删除考试' else f"{name}（已删除考试）", archived=True,
                 minutes=amount, total_tasks=0, done_tasks=0, rate=0.0)
            for name, amount in sorted(minutes.items())]
