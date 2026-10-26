"""RFC 5545 文本处理；本系统按亚洲/上海日期导入单次学习事件。"""
from datetime import date, datetime, timedelta, timezone
from math import ceil
from zoneinfo import ZoneInfo

from icalendar import Calendar

LOCAL_ZONE = ZoneInfo("Asia/Shanghai")


def parse_events(text: str) -> tuple[list[dict], int]:
    try:
        calendar = Calendar.from_ical(text)
    except (ValueError, TypeError) as exc:
        raise ValueError("日历文件格式无效") from exc
    if calendar.name != "VCALENDAR":
        raise ValueError("需要完整的 VCALENDAR 文件")
    components = calendar.walk("VEVENT")
    if len(components) > 500:
        raise ValueError("一次最多导入 500 个事件，请拆分文件")
    events, skipped, seen = [], 0, set()
    for component in components:
        if component.errors:
            raise ValueError("日历事件含无效字段，请修正后重试")
        if any(key in component for key in ("RRULE", "RDATE", "EXDATE", "RECURRENCE-ID")):
            raise ValueError("暂不导入重复规则，请先在日历软件中展开为单次事件")
        if str(component.get("STATUS", "")).upper() == "CANCELLED":
            skipped += 1
            continue
        title = str(component.get("SUMMARY", "")).strip()
        start = component.decoded("DTSTART", None)
        if not title or start is None:
            raise ValueError("每个日历事件都需要标题和有效开始日期")
        if len(title) > 251:
            raise ValueError("日历事件标题最多 251 字，请缩短后导入")
        if isinstance(start, datetime):
            end = component.decoded("DTEND", None)
            duration = component.decoded("DURATION", None)
            if end is not None and duration is not None:
                raise ValueError("日历事件不能同时指定结束时刻和持续时间")
            if duration is not None and not isinstance(duration, timedelta):
                raise ValueError("日历事件持续时间无效")
            start = start.replace(tzinfo=LOCAL_ZONE) if start.tzinfo is None else start.astimezone(LOCAL_ZONE)
            if end is not None:
                if not isinstance(end, datetime):
                    raise ValueError("事件开始和结束必须使用相同日期类型")
                end = end.replace(tzinfo=LOCAL_ZONE) if end.tzinfo is None else end.astimezone(LOCAL_ZONE)
                duration = end.astimezone(timezone.utc) - start.astimezone(timezone.utc)
            minutes = ceil((duration if duration is not None else timedelta(hours=1)).total_seconds() / 60)
            day = start.date()
        elif isinstance(start, date):
            day, minutes = start, 60
            end = component.decoded("DTEND", None)
            if end is not None and (isinstance(end, datetime) or end <= start):
                raise ValueError("全天事件结束日期必须晚于开始日期")
        else:
            raise ValueError("日历开始日期无效")
        if not 1 <= minutes <= 1440:
            raise ValueError("单个学习事件时长需在 1～1440 分钟之间")
        key = (title, day.isoformat(), minutes)
        if key in seen:
            skipped += 1
            continue
        seen.add(key)
        events.append(dict(title=title, day=day.isoformat(), minutes=minutes))
    if not events:
        raise ValueError("文件中没有可导入的单次事件")
    return events, skipped


def escape_text(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,")


def fold_line(value: str) -> str:
    # 按 UTF-8 字节计数，并保证不在多字节字符中间折行。
    lines, current, size = [], "", 0
    for character in value:
        length = len(character.encode("utf-8"))
        if size + length > 75:
            lines.append(current)
            current, size = " ", 1
        current += character
        size += length
    return "\r\n".join([*lines, current])


def export_calendar(exams, tasks, user_id: int) -> bytes:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//fmzh//Study Calendar//CN", "CALSCALE:GREGORIAN", "X-WR-CALNAME:" + escape_text("期末周别慌！备考日历")]
    subjects = {exam.id: exam.subject for exam in exams}
    for exam in exams:
        lines.extend(["BEGIN:VEVENT", f"UID:exam-{exam.id}-{user_id}@fmzh", f"DTSTAMP:{stamp}",
                      f"DTSTART;VALUE=DATE:{exam.exam_date:%Y%m%d}",
                      f"DTEND;VALUE=DATE:{exam.exam_date + timedelta(days=1):%Y%m%d}",
                      "SUMMARY:" + escape_text("【考试】" + exam.subject),
                      "LOCATION:" + escape_text(exam.location or "地点待定"),
                      "DESCRIPTION:" + escape_text(f"时长 {exam.duration_minutes} 分钟｜{exam.note or ''}"), "END:VEVENT"])
    for task in tasks:
        # 当前任务只有日期，08:00 是日历展示占位，不声称任务有实际起止时刻。
        start = datetime.combine(task.plan_date, datetime.min.time(), tzinfo=LOCAL_ZONE) + timedelta(hours=8)
        end = start + timedelta(minutes=task.estimated_minutes)
        subject = subjects.get(task.exam_id, "")
        lines.extend(["BEGIN:VEVENT", f"UID:task-{task.id}-{user_id}@fmzh", f"DTSTAMP:{stamp}",
                      f"DTSTART:{start.astimezone(timezone.utc):%Y%m%dT%H%M%SZ}",
                      f"DTEND:{end.astimezone(timezone.utc):%Y%m%dT%H%M%SZ}",
                      "SUMMARY:" + escape_text("【任务】" + (subject + "·" if subject else "") + task.title),
                      "DESCRIPTION:" + escape_text(f"{'已完成' if task.is_done else '未完成'}｜预计 {task.estimated_minutes} 分钟；08:00 仅为展示占位"), "END:VEVENT"])
    return ("\r\n".join(fold_line(line) for line in [*lines, "END:VCALENDAR"]) + "\r\n").encode("utf-8")
