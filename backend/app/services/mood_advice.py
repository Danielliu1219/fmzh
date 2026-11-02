"""既定情绪公式的展示建议；分档与触发均使用未舍入评分。"""

RHYTHM = (
    "先暂停一下，今天从一小段轻松复习开始。",
    "把任务拆小，每学习十分钟就休息一会儿。",
    "优先回顾熟悉的概念，暂缓需要长时间攻坚的内容。",
    "减少今日任务，先做一项最有把握的基础练习。",
    "放慢复习节奏，穿插休息，允许自己留一点余量。",
    "保持轻量节奏，先完成核心任务再决定是否继续。",
    "按当前计划稳步推进，学习与休息交替进行。",
    "状态平稳，可以增加一次错题回顾或自测。",
    "状态很好，完成基础后再挑战综合题。",
    "保持当前节奏，适度挑战难点并留好休息时间。",
)
PLANS = (
    "优先暂停半天或只保留一项核心任务；可预览减负后再确认。",
    "减轻当日任务，把低优先级内容移到后续可用时间。",
    "保持当前总时长，先做高权重内容，预留机动时间。",
    "保持原有预算，完成后再选择拓展内容，不自动加量。",
)
SUPPORT = (
    "一次考试不能定义你，先照顾好眼前的一小步。",
    "累的时候休息，是复习计划的一部分。",
    "不必和别人的进度比较，按自己的节奏前进。",
    "已经完成的每一点，都值得被看见。",
    "遇到困难时，可以和同学或信任的人聊一聊。",
    "今天不必解决所有问题，先选一件能完成的事。",
    "留一点时间吃饭、喝水和活动，让身体跟得上。",
    "允许状态起伏，明天还可以重新安排。",
)


def advice(raw, day, user_id, previous):
    band = min(9, max(0, int(raw * 2)))
    level = 0 if raw < 1.5 else 1 if raw < 2.5 else 2 if raw < 4 else 3
    low_days = 0
    if raw < 2.5:
        low_days = 1
        from datetime import timedelta

        cursor = day - timedelta(days=1)
        while previous.get(cursor) is not None and previous[cursor] < 2.5:
            low_days += 1
            cursor -= timedelta(days=1)
    return dict(
        band=band + 1,
        plan_level=level + 1,
        suggestion=RHYTHM[band],
        plan_suggestion=PLANS[level],
        support_message=SUPPORT[(day.toordinal() + user_id) % 8],
        low_days=low_days,
        need_emergency=low_days >= 3,
    )
