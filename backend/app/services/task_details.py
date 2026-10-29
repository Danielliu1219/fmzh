"""任务时段与有限重复规则；全部按北京时间、同日整分钟处理。"""
import re
from datetime import date, time, timedelta

REPEAT_RULES = {'none', 'daily', 'weekdays', 'weekly'}
DETAIL_FIELDS = ('start_time', 'end_time', 'location', 'difficulty', 'detail')
SNAPSHOT_FIELDS = ('id', 'exam_id', 'title', 'plan_date', 'estimated_minutes', 'priority', 'source', 'is_done',
                   *DETAIL_FIELDS, 'repeat_rule', 'repeat_until', 'repeat_group_id')


def task_time(value):
    if value is None:
        return None
    if isinstance(value, str):
        if not re.fullmatch(r'\d{2}:\d{2}', value):
            raise ValueError('任务时间请使用 HH:mm，按北京时间填写')
        try:
            value = time.fromisoformat(value)
        except ValueError:
            raise ValueError('任务时间无效')
    if not isinstance(value, time) or value.second or value.microsecond or value.tzinfo:
        raise ValueError('任务时间需为北京时间的整分钟，不带时区')
    return value


def timed_minutes(start, end):
    if (start is None) != (end is None):
        raise ValueError('开始时间和结束时间需一起填写，或一起清空')
    if start is None:
        return None
    start, end = task_time(start), task_time(end)
    minutes = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
    if minutes <= 0:
        raise ValueError('结束时间需晚于开始时间；跨午夜任务请拆成两天')
    return minutes


def occurrence_dates(start, rule='none', until=None):
    if rule not in REPEAT_RULES:
        raise ValueError('不支持的重复规则')
    if rule == 'none':
        if until is not None:
            raise ValueError('单次任务不需要重复截止日')
        return [start]
    if until is None or until < start:
        raise ValueError('重复截止日需填写，且不能早于开始日期')
    if (until - start).days > 365:
        raise ValueError('重复任务的日期范围最多一年')
    days = []
    current = start
    while current <= until:
        if rule == 'daily' or (rule == 'weekdays' and current.weekday() < 5) or (rule == 'weekly' and current.weekday() == start.weekday()):
            days.append(current)
        if len(days) > 180:
            raise ValueError('一次最多创建180项重复任务，请缩短截止日期')
        if current == until:
            break
        current += timedelta(days=1)
    if not days:
        raise ValueError('该日期范围内没有符合重复规则的日期')
    return days
