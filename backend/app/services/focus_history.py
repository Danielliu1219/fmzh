"""已删除考试保留科目名和分钟数，不混入自由专注或新的掌握度评测。"""
from collections import defaultdict
from datetime import datetime, time, timedelta
from types import SimpleNamespace


def counted_sessions(rows, start, end):
    """统计有效区间：跨科去重、按自然日切分；原始历史记录不删除。"""
    covered_until=None
    result=[]
    legacy=set()
    for row in sorted(rows,key=lambda r:(r.start_time,r.id)):
        a,b=row.start_time,row.end_time
        values={c.name:getattr(row,c.name) for c in row.__table__.columns}
        if (b-a).total_seconds()<1:
            # 早期导入记录可能只有可用的分钟数，不能因时间戳缺陷抹去其学习记录。
            key=(a.replace(microsecond=0),b.replace(microsecond=0),row.exam_id,row.duration_minutes)
            if start<=a<end and key not in legacy:
                result.append(SimpleNamespace(**values));legacy.add(key)
            continue
        b=min(b,a+timedelta(minutes=row.duration_minutes))
        x,y=max(start,a,covered_until or a),min(end,b)
        chunks=[(x,y)] if x<y else []
        covered_until=max(covered_until or b,b)
        for x,y in chunks:
            while x<y:
                stop=min(y,datetime.combine(x.date()+timedelta(days=1),time.min))
                minutes=int((stop-x).total_seconds()/60+1e-7)
                if minutes:
                    result.append(SimpleNamespace(**{**values,'start_time':x,'end_time':stop,'duration_minutes':minutes}))
                x=stop
    return result


def archived_subjects(sessions):
    minutes = defaultdict(int)
    for session in sessions:
        if session.exam_id is None and session.subject_snapshot:
            minutes[session.subject_snapshot] += session.duration_minutes
    return [dict(exam_id=None, subject=name if name == '已删除考试' else f"{name}（已删除考试）", archived=True,
                 minutes=amount, total_tasks=0, done_tasks=0, rate=0.0)
            for name, amount in sorted(minutes.items())]
