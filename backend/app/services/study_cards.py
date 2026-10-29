"""思维导图与记忆卡片（用例 4.4 / FMZH-USR-0036）

基于最近一次 AI 分析结果与资料正文生成：
- 思维导图：课程 → 知识点 / 考点 → 依据与建议投入，便于提纲式回顾
- 记忆卡片：正面为知识点或考点，背面优先摘取资料正文中的相关句子，
  取不到时退回分析结论里的依据说明，保证每张卡都有可背诵内容。
"""
import re

CARD_BACK_LIMIT = 180


def _suggested_time(point):
    if point.suggest_minutes is None:
        return f'{point.suggest_hours} 小时'
    return f'{point.suggest_minutes} 分钟' if point.suggest_minutes else '本轮暂不安排'


def _excerpt(text: str, keyword: str, limit: int = CARD_BACK_LIMIT) -> str:
    """在资料正文中截取关键词附近的句子，作为卡片背面内容"""
    text = (text or "").strip()
    keyword = (keyword or "").strip()
    if not text or not keyword:
        return ""
    index = text.find(keyword)
    if index < 0:
        return ""
    start = max(0, index - 50)
    end = min(len(text), index + len(keyword) + 120)
    snippet = re.sub(r"\s+", " ", text[start:end]).strip()
    if len(snippet) > limit:
        snippet = snippet[:limit].rstrip() + "…"
    return f"{'…' if start > 0 else ''}{snippet}{'…' if end < len(text) else ''}"


def build_mindmap(course: str, result, material_texts: list[str]) -> dict:
    """课程 → 知识点 / 考点 → 依据、建议投入"""
    knowledge_points = sorted(result.knowledge_points, key=lambda kp: kp.weight, reverse=True)
    kp_nodes = []
    for kp in knowledge_points:
        children = []
        if kp.recommend_reason:
            children.append({"name": f"依据：{kp.recommend_reason}"})
        if kp.suggest_hours or kp.suggest_minutes is not None:
            children.append({"name": f"建议投入：{_suggested_time(kp)}"})
        kp_nodes.append(
            {
                "name": f"{kp.name}（{round(kp.weight * 100)}%）",
                "value": kp.weight,
                "level": kp.importance,
                "source": kp.source,
                "children": children,
            }
        )

    focus_nodes = []
    for focus in result.exam_focus:
        children = [{"name": f"依据：{focus.basis}"}] if focus.basis else []
        focus_nodes.append(
            {
                "name": f"{'必考' if focus.level == 'must' else '常考'}：{focus.content}",
                "level": focus.level,
                "source": focus.source,
                "children": children,
            }
        )

    return {
        "name": course or result.course,
        "children": [
            {"name": "知识点", "children": kp_nodes},
            {"name": "考点", "children": focus_nodes},
        ],
    }


def build_cards(result, material_texts: list[str]) -> list[dict]:
    """知识点 / 考点 → 记忆卡片（正面提示，背面资料依据）"""
    body = "\n".join(text for text in material_texts if text)
    cards: list[dict] = []
    seen: set[str] = set()

    for kp in sorted(result.knowledge_points, key=lambda item: item.weight, reverse=True):
        if not kp.name or kp.name in seen:
            continue
        back = _excerpt(body, kp.name) or kp.recommend_reason or "结合资料复习该知识点"
        cards.append(
            {
                "id": len(cards) + 1,
                "front": kp.name,
                "back": back,
                "hint": f"依据来源：{kp.source or '所上传复习资料'} · 建议投入 {_suggested_time(kp)}",
                "knowledge_point": kp.name,
                "source": kp.source,
            }
        )
        seen.add(kp.name)

    for focus in result.exam_focus:
        if not focus.content or focus.content in seen:
            continue
        # 考点内容通常较长，取开头片段做正文匹配，匹配不到再用判断依据
        back = _excerpt(body, focus.content[:8]) or focus.basis or "结合资料复习该考点"
        cards.append(
            {
                "id": len(cards) + 1,
                "front": focus.content,
                "back": back,
                "hint": f"来源：{focus.source or '所上传复习资料'} · {'必考' if focus.level == 'must' else '常考'}",
                "knowledge_point": "",
                "source": focus.source,
            }
        )
        seen.add(focus.content)

    return cards
