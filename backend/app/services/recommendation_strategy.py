"""在既有目标/绩点定义之上分配复习内容；不改成绩区间，不增加任务总时长。"""
import json
import math
from collections import defaultdict
from datetime import date, timedelta

from ..schemas.schemas import PlanActivity, StudyPhase, StudyStrategy
from .score_targets import SCORE_BANDS, band_text

PHASES = (
    ('foundation', '基础巩固', '核对本主题的概念、公式与适用条件，跟做资料中的基础例题'),
    ('practice', '常见题型与错题', '独立完成资料中的常见题型，核对步骤并复盘错误原因'),
    ('challenge', '综合与限时训练', '在基础题能独立完成后，练习资料中的综合应用或限时题；缺少相应题目时用于错题复盘'),
)


def split_minutes(total, weights):
    """最大余数分配，允许零分钟；小预算也不能被每项最低时长撑大。"""
    if not weights:
        return []
    total = max(0, int(total))
    denominator = sum(weights)
    if denominator <= 0:
        weights = [1] * len(weights)
        denominator = len(weights)
    exact = [total * w / denominator for w in weights]
    allocated = [math.floor(x) for x in exact]
    order = sorted(range(len(weights)), key=lambda i: (-(exact[i] - allocated[i]), i))
    for i in order[:total - sum(allocated)]:
        allocated[i] += 1
    return allocated


def strategy_for(profile):
    band = getattr(profile, 'target_band', None)
    minimum = SCORE_BANDS[band][0] if band in SCORE_BANDS else {'pass': 60, 'medium': 76, 'high': 90}.get(profile.target, 76)
    progress = max(0, min(1, (minimum - 60) / 30))
    # 连续调整练习深度，而不是另建十套题库或改变绩点分档。
    foundation = math.floor(65 - 40 * progress + .5)
    practice = math.floor(30 + 10 * progress + .5)
    status = getattr(profile, 'learning_status', None) or 'medium'
    foundation += {'weak': 12, 'good': -8}.get(status, 0)
    foundation = min(85, max(15, foundation))
    practice = min(practice, 100 - foundation)
    challenge = 100 - foundation - practice
    days = max(1, min(366, int(profile.available_days or 1)))
    if days <= 3 and challenge > 10:
        practice += challenge - 10
        challenge = 10
    weak = getattr(profile, 'weak_chapters', []) or []
    if isinstance(weak, str):
        try:
            weak = json.loads(weak)
        except (ValueError, TypeError):
            weak = []
    weak = [str(x).strip()[:80] for x in weak if str(x).strip()] if isinstance(weak, list) else []
    daily = max(0, min(960, math.floor(float(profile.daily_hours or 0) * 60 + 1e-7)))
    return StudyStrategy(
        target_band=band if band in SCORE_BANDS else None,
        target_label=band_text(band) or {'pass': '保及格', 'medium': '稳中等', 'high': '冲高分'}.get(profile.target, '稳中等'),
        learning_status=status, available_days=days, daily_minutes=daily,
        available_minutes=daily * days, weak_chapters=weak,
        phases=[StudyPhase(phase=key, label=label, percent=percent, detail=detail)
                for (key, label, detail), percent in zip(PHASES, (foundation, practice, challenge))],
        notes=['三类练习拆分同一份计划时间，不额外增加每日任务量；比例为复习建议，不代表试卷分值或题型出现频率。',
               '高目标也先补基础；临考三天内优先常见题与错题，资料未覆盖的难题不另行编造。'],
    )


def strategy_context(profile):
    strategy = strategy_for(profile)
    phases = '；'.join(f'{p.label} {p.percent}%：{p.detail}' for p in strategy.phases)
    return (f'\n【复习内容与时间侧重】目标 {strategy.target_label}；{phases}。'
            f'优先补足薄弱章节：{ "、".join(strategy.weak_chapters) or "未明确指定" }。'
            '以上比例用于同一任务内部的时间拆分，不是新增任务，也不是对试卷题数/占比的估计；不得修改资料中的题型频次或引文。')


def refresh_strategy(result):
    """重排后按当前计划更新分钟，保留生成时的目标和练习比例。"""
    strategy = result.strategy
    if strategy is None:
        return
    for phase in strategy.phases:
        phase.minutes = 0
    for item in result.review_plan:
        amounts = split_minutes(item.estimated_minutes, [p.percent for p in strategy.phases])
        item.activities = [PlanActivity(phase=p.phase, label=p.label, minutes=n, detail=p.detail)
                           for p, n in zip(strategy.phases, amounts) if n]
        for phase, amount in zip(strategy.phases, amounts):
            phase.minutes += amount
    strategy.planned_minutes = sum(p.estimated_minutes for p in result.review_plan)
    scores = []
    for point in result.knowledge_points:
        weak = any(len(c) >= 2 and (c in point.name or point.name in c) for c in strategy.weak_chapters)
        # 来源权重仍是原始数据；只调整学习时间，不伪造更高出现频率。
        score = max(.05, point.weight) ** (1 + strategy.phases[0].percent / 100) * (1.6 if weak else 1)
        scores.append(score)
        point.practice_hint = ('你标注的薄弱内容，先补概念和典型例题，再独立练习。' if weak else
                               '先完成资料中的高频基础题，再按本轮比例练习与复盘。')
    amounts = split_minutes(strategy.planned_minutes, scores)
    for point, amount in zip(result.knowledge_points, amounts):
        point.suggest_minutes = amount
        point.suggest_hours = round(amount / 60, 2)


def apply_strategy(result, profile, today=None):
    """收口模型结果：按天累计限额，说明未安排部分，再生成等量的练习拆分。"""
    today = today or date.today()
    strategy = strategy_for(profile)
    result.strategy = strategy
    load = defaultdict(int)
    plan = []
    for original in result.review_plan:
        requested = max(0, int(original.estimated_minutes))
        index = original.day - 1
        if not 0 <= index < strategy.available_days:
            strategy.deferred_minutes += requested
            continue
        amount = min(requested, max(0, strategy.daily_minutes - load[index]))
        strategy.deferred_minutes += requested - amount
        if not amount:
            continue
        item = original.model_copy(deep=True)
        item.date = (today + timedelta(days=index)).isoformat()
        item.estimated_minutes = amount
        item.priority = max(1, min(3, item.priority))
        load[index] += amount
        plan.append(item)
    result.review_plan = plan
    refresh_strategy(result)
    if strategy.deferred_minutes:
        strategy.notes.append(f'模型原建议中有 {strategy.deferred_minutes} 分钟超出本科生成时的可用天数或当日份额，未写入任务；请缩小复习范围或调整预算后重新生成。')
    result.summary = f'目标：{strategy.target_label}。' + result.summary
