"""只读学习习惯统计。打卡是完成时刻，不能代替专注区间或证明学习效率。"""
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone

from ..models.models import Exam, FocusSession, Task
from .study_planner import daily_budget

CHINA = timezone(timedelta(hours=8))
MIN_DAYS, MIN_SESSIONS, MIN_MINUTES = 3, 5, 90


def local_time(value):
    # 历史无时区记录沿用服务器本地时间；新带时区数据统一为北京时间。
    return value.astimezone(CHINA).replace(tzinfo=None) if value.tzinfo else value


def summarize(sessions, budget, now=None):
    now = local_time(now or datetime.now(CHINA))
    start = datetime.combine(now.date() - timedelta(days=27), time.min)
    intervals, seen = [], set()
    ignored = 0
    for row in sessions:
        a, b = local_time(row.start_time), local_time(row.end_time)
        duration = row.duration_minutes
        # 异常、未来、时长不一致记录不作为推荐依据；跨窗口记录只计交集。
        if b <= start or a >= now:
            continue
        if (not 1 <= duration <= 180 or b <= a or b > now
                or abs((b-a).total_seconds()/60-duration) > 1):
            ignored += 1
            continue
        a = max(a, start)
        key = (a, b)
        if key in seen:
            ignored += 1
            continue
        seen.add(key)
        intervals.append(key)

    merged = []
    for a, b in sorted(intervals):
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    seconds, days = defaultdict(float), defaultdict(set)
    study_days = set()
    for a, b in merged:
        while a < b:
            boundary = a.replace(hour=(a.hour//2)*2, minute=0, second=0, microsecond=0) + timedelta(hours=2)
            end = min(b, boundary)
            index = a.hour//2
            seconds[index] += (end-a).total_seconds()
            days[index].add(a.date())
            study_days.add(a.date())
            a = end
    total = int(sum(seconds.values())//60)
    candidates = [i for i in seconds if len(days[i]) >= 2 and seconds[i] >= 20*60]
    enough = len(study_days) >= MIN_DAYS and len(intervals) >= MIN_SESSIONS and total >= MIN_MINUTES and bool(candidates)
    chosen = sorted(candidates, key=lambda i: (-seconds[i], -len(days[i]), i))[:3] if enough else [None]*3
    slots = []
    remaining = budget
    for index, i in enumerate(chosen):
        if remaining <= 0:
            break
        hour = i*2 if i is not None else [9, 14, 19][index]
        amount = min(120, remaining, max(1, (budget+len(chosen)-1)//len(chosen)))
        remaining -= amount
        end = hour+2
        evidence = int(seconds[i]//60) if i is not None else 0
        count = len(days[i]) if i is not None else 0
        slots.append(dict(name=f'习惯时段 {index+1}' if enough else ['上午', '下午', '晚上'][index],
                          start=f'{hour:02d}:00', end=f'{end:02d}:00', minutes=amount,
                          focus='选择一项重点任务，中间留出休息时间', history_minutes=evidence,
                          study_days=count, reason=f'近28天有{count}天在此专注，累计{evidence}分钟' if enough else '通用参考时段，尚无足够个人记录'))
    note = ('根据重复出现的专注时段推荐，只反映习惯，不代表效率或空闲时间。' if enough else
            f'记录不足：近28天有效专注{len(intervals)}条、{len(study_days)}天、{total}分钟；至少需5条、3天、90分钟，且同一时段在2天出现并累计20分钟。暂显示通用参考。')
    if remaining:
        note += f' 还有{remaining}分钟预算未分配，请按实际作息另行安排。'
    if ignored:
        note += f' 已忽略{ignored}条重复或异常记录。'
    return dict(daily_hours=budget/60, daily_minutes=budget, mode='history' if enough else 'insufficient',
                window_start=start.date().isoformat(), window_end=now.date().isoformat(), timezone='Asia/Shanghai',
                session_count=len(intervals), study_days=len(study_days), history_minutes=total,
                ignored_sessions=ignored, recommended_minutes=budget-remaining, unallocated_minutes=remaining,
                slots=slots, note=note)


def recommend(db, user_id, exam_id=None, now=None):
    now = local_time(now or datetime.now(CHINA))
    start = datetime.combine(now.date()-timedelta(days=27), time.min)
    sessions = db.query(FocusSession).filter(FocusSession.user_id == user_id, FocusSession.end_time > start)
    checkins = db.query(Task).join(Exam, Task.exam_id == Exam.id).filter(
        Exam.user_id == user_id, Task.user_id == user_id, Task.is_done.is_(True), Task.done_at >= start, Task.done_at <= now)
    if exam_id is not None:
        sessions = sessions.filter(FocusSession.exam_id == exam_id)
        checkins = checkins.filter(Task.exam_id == exam_id)
    result = summarize(sessions.all(), daily_budget(db, user_id), now)
    result.update(exam_id=exam_id, scope='course' if exam_id is not None else 'all', checkin_count=checkins.count())
    result['note'] += ' 打卡仅统计完成次数，不推算专注时长；推荐不会改动任务安排。'
    return result
