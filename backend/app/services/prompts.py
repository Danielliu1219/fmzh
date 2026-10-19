"""大模型提示词模板 + Mock 数据

两次调用的输出都必须符合 schemas.py 中定义的固定 JSON 结构：
- 第一次：自然语言 -> 用户画像（ProfileOut 对应字段）
- 第二次：画像 + 资料 -> 复习分析（AnalysisResult）

LLM_MOCK=true 时使用本文件的启发式提取器/示例数据，无需 API Key。
"""
import json
import re
from datetime import date, timedelta
from .score_targets import band_text

# ==================== 第一次调用：画像提取 ====================

PROFILE_SYSTEM_PROMPT = """你是"期末周别慌"系统的信息提取助手。用户会用自然语言描述自己的期末复习情况，请你提取成 JSON 对象。

要求：
1. target（备考目标）：只能取 "pass"（保及格）、"medium"（稳中等）、"high"（冲高分）之一；用户没提到就填 null。
2. learning_status（基础水平）：只能取 "weak"（薄弱）、"medium"（一般）、"good"（良好）之一；用户没提到就填 null。
3. available_days（距考试剩余天数）：整数；用户没提到就填 null。
4. daily_hours（每天能投入的小时数）：数字；用户没提到就填 null。
5. weak_chapters（薄弱章节）：字符串数组，从用户描述中提取，没有就填空数组。
6. output_need（期望的输出）：默认 ["知识点权重", "复习计划", "自测题"]，用户明确只想要某几项时按需填写。
7. 只输出 JSON 对象，不要输出任何其他文字或解释。"""


def build_profile_user_prompt(exam_subject: str, raw_text: str) -> str:
    return f"考试科目：{exam_subject}\n用户描述：{raw_text}"


# Mock：用简单规则模拟"自然语言 -> JSON"，故意提取不到的部分留 None，
# 这样"画像不完整 -> 前端补全"的流程在 Mock 模式下也能真实演示
_CN_NUM = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _extract_days(text: str):
    m = re.search(r"(\d+)\s*天", text)
    if m:
        return int(m.group(1))
    m = re.search(r"([一两二三四五六七八九十]+)\s*天", text)
    if m:
        s = m.group(1)
        if len(s) == 1:
            return _CN_NUM.get(s)
        if s == "十":
            return 10
        if s.startswith("十") and len(s) == 2:
            return 10 + _CN_NUM.get(s[1], 0)
        if s.endswith("十") and len(s) == 2:
            return 10 * _CN_NUM.get(s[0], 1)
    return None


def _extract_hours(text: str):
    # 阿拉伯数字：2小时 / 2.5 小时 / 2 个小时 / 2h
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:小时|钟头|个小时|\s*h\b)", text)
    if m:
        return float(m.group(1))
    # 中文数字：两小时 / 两个半小时 / 三个小时
    m = re.search(r"([一两二三四五六七八九十])\s*(?:个\s*)?(半\s*)?(?:小时|钟头)", text)
    if m and m.group(1) in _CN_NUM:
        val = _CN_NUM[m.group(1)]
        if m.group(2):
            val += 0.5
        return float(val)
    return None


def mock_extract_profile(raw_text: str) -> dict:
    """Mock 画像提取：基于关键词规则，提取不到的字段为 None"""
    if re.search(r"及格|过线|60\s*分|不挂", raw_text):
        target = "pass"
    elif re.search(r"高分|优秀|90|满绩|保研|冲一冲", raw_text):
        target = "high"
    elif re.search(r"中等|80|良好|中游", raw_text):
        target = "medium"
    else:
        target = None

    if re.search(r"没学|没怎么学|不会|零基础|基本没|基础差|很差|没听过", raw_text):
        learning_status = "weak"
    elif re.search(r"还行|一般|中等|马马虎虎|差不多|学过一点", raw_text):
        learning_status = "medium"
    elif re.search(r"不错|掌握|熟练|挺好|很好|学过|基础好|扎实", raw_text):
        learning_status = "good"
    else:
        learning_status = None

    weak_chapters = []
    # 句式一：关键词在前，如"薄弱的是极限、积分"
    m = re.search(r"(?:薄弱|很差)(?:的是|在|：|:)?([^，。；;！!？?\n]{2,40})", raw_text)
    if m:
        weak_chapters += [c.strip() for c in re.split(r"[、,，和及与]", m.group(1)) if c.strip()]
    # 句式二：关键词在后，如"极限和积分不太会"
    for m in re.finditer(r"([^，。；;！!？?\n]{2,40}?)(?:不太会|不太懂|不会|搞不懂|没学好|没学懂)", raw_text):
        seg = m.group(1).strip()
        # 排除"我这门课基本没学"这类句子主干，只保留章节名
        if seg and not re.search(r"[我你他她它想只基本学过门课]", seg):
            weak_chapters += [c.strip() for c in re.split(r"[、,，和及与]", seg) if c.strip()]
    weak_chapters = [c for c in dict.fromkeys(weak_chapters) if len(c) <= 20][:10]

    return {
        "target": target,
        "learning_status": learning_status,
        "available_days": _extract_days(raw_text),
        "daily_hours": _extract_hours(raw_text),
        "weak_chapters": weak_chapters,
        "output_need": ["知识点权重", "复习计划", "自测题"],
    }


# ==================== 第二次调用：复习分析 ====================

ANALYZE_SYSTEM_PROMPT = """你是"期末周别慌"系统的复习分析助手。请根据用户画像和用户上传的复习资料，生成个性化复习方案。

输出要求（严格 JSON，不要输出任何其他文字）：
{
  "course": "课程名",
  "summary": "一段话总评，说明总体策略（例如：基础薄弱求及格，优先高频基础内容）",
  "knowledge_points": [
    {"name": "知识点名", "weight": 0.9, "importance": "high", "recommend_reason": "推荐理由", "source": "历年题/老师重点/平时作业/课堂笔记/教材章节/实验报告/练习题/其他", "suggest_hours": 6}
  ],
  "exam_focus": [
    {"content": "必考/常考内容描述", "level": "must", "basis": "判断依据", "source": "历年题", "frequency": 4}
  ],
  "question_types": [
    {"type": "计算题", "count": 8, "frequency": 0.4, "basis": "近 4 年每年约 2 道", "source": "历年题"}
  ],
  "review_plan": [
    {"day": 1, "date": "2026-09-08", "title": "当天复习主题", "estimated_minutes": 180, "priority": 1, "detail": "具体做什么"}
  ],
  "quiz": [
    {"kind": "single", "question": "题目", "options": ["A. ...", "B. ...", "C. ...", "D. ..."], "answer": "B", "analysis": "解析", "knowledge_point": "对应知识点", "accepted_answers": []}
  ]
}

约束：
1. weight 取值范围 0~1；importance 只取 high/medium/low。
2. level 只取 must（必考）/common（常考）。
3. 所有推荐必须基于用户上传的资料内容，并注明 source（出自哪类资料）；资料里没有的依据不要编造，可以在 summary 中说明资料不足。资料头部的资料权重表示参考可信度，优先参考高权重内容；明确标注资料标题与来源，不能捏造出处。
4. review_plan 必须严格按用户画像定制：优先遵循用户明确选择的分数区间与绩点目标，按区间调整知识点覆盖、练习深度和难题比例；及格目标且基础 weak 时，优先高频基础内容、适当压缩任务量，高区间加入综合题、难题和易错点。计划天数不超过 available_days，每天任务量不超过 daily_hours*60 分钟。
5. 自测题 3~5 道，贴合历年题型与资料内容。kind 只取 single（单选）、multiple（多选）、boolean（判断）、fill（填空）；单/多选 options 按 A/B/C 顺序，answer 为选项字母，多选用 A,C 格式；判断答案为 true 或 false；填空答案必须确定，accepted_answers 可列明确等价写法。不要生成需要主观评分的题。
6. question_types 必须基于历年题/练习题等资料统计题型分布：type 取选择题/填空题/计算题/证明题/应用题/简答题/综合题；count 为可识别的题数或出现次数，frequency 为占比 0~1；没有可核实题型数据时返回空列表并说明资料不足，不能编造题数。exam_focus.frequency 只填写可核实的出现次数/年份数。
7. recommend_reason 和 exam_focus.basis 必须写明依据来源（例如「历年题近 3 年每年出现」「老师标注重点」「画像中的薄弱章节」），不能只写“重要/常考”这类空话；每个结论都要让学生看得出依据是什么。
8. 生成内容仅供复习参考，提示用户结合教材与课堂要求。"""


def build_analyze_user_prompt(profile_text: str, materials_text: str) -> str:
    return (
        "【用户画像】\n"
        f"{profile_text}\n\n"
        "【复习资料】（格式：资料标题 [来源类型｜资料权重] 内容…）\n"
        f"{materials_text}"
    )


def mock_generate_analysis(subject: str, profile: dict) -> dict:
    """Mock 分析：返回结构完整、内容通用的示例数据（标注了 Mock）"""
    today = date.today()
    kp_templates = [
        ("核心概念与定义", 0.95, "high", "历年题多次出现，属于必得分内容", "历年题"),
        ("高频计算与解题方法", 0.9, "high", "老师课堂上反复强调", "老师重点"),
        ("重点公式与定理", 0.8, "medium", "平时作业和练习题覆盖率高", "平时作业"),
        ("综合应用题", 0.6, "medium", "历年题最后一道大题常考", "历年题"),
        ("拓展与易错点", 0.4, "low", "课堂笔记中标注的易错内容", "课堂笔记"),
    ]
    # 三档策略在 Mock 里也给出不同的计划主题（用例 4.11）
    plan_by_target = {
        "pass": [
            "过一遍必考基础概念",
            "刷高频基础题",
            "巩固必得分题型",
            "错题回顾",
            "整体回顾 + 基础自测",
        ],
        "medium": [
            "过一遍核心概念与公式",
            "刷高频基础题",
            "专项突破薄弱章节",
            "做综合题与易错点",
            "整体回顾 + 自测查漏",
        ],
        "high": [
            "梳理高频考点与知识框架",
            "重点章节专项突破",
            "综合题训练",
            "难题与易错点突破",
            "限时模考 + 错题复盘",
        ],
    }
    plan_titles = plan_by_target.get(getattr(profile, "target", None), plan_by_target["medium"])
    strategy = getattr(profile, "target", "pass")
    goal = band_text(getattr(profile, "target_band", None))
    focus_templates = [
        ("核心概念的定义与辨析", "must", "近三年历年题每年必考", "历年题", 4),
        ("高频题型的基本解法", "must", "老师划的重点内容", "老师重点", 3),
        ("平时作业中出现过的同类题", "common", "平时作业与练习册高频出现", "平时作业", 2),
    ]
    question_types = [
        {"type": "选择题", "count": 10, "frequency": 0.25, "basis": "历年题选择题约占四分之一", "source": "历年题"},
        {"type": "填空题", "count": 6, "frequency": 0.15, "basis": "历年题填空题稳定出现", "source": "历年题"},
        {"type": "计算题", "count": 16, "frequency": 0.4, "basis": "历年题计算题占比最高", "source": "历年题"},
        {"type": "证明题", "count": 4, "frequency": 0.1, "basis": "历年题证明题每年约 1 道", "source": "历年题"},
        {"type": "应用题", "count": 4, "frequency": 0.1, "basis": "历年题末段常应用题", "source": "历年题"},
    ]
    quiz_templates = [
        {
            "question": f"（Mock）关于{subject}核心概念的描述，下列说法正确的是？",
            "options": ["A. 只需记忆不需理解", "B. 理解概念并结合例题掌握", "C. 考试不会考概念", "D. 概念与解题无关"],
            "answer": "B",
            "analysis": "核心概念是解题的基础，历年题表明概念辨析是高频考点。",
            "knowledge_point": "核心概念与定义",
        },
        {
            "question": f"（Mock）复习{subject}时，基础薄弱的同学应该优先做什么？",
            "options": ["A. 直接刷难题", "B. 先掌握高频基础内容", "C. 只背答案", "D. 放弃计算题"],
            "answer": "B",
            "analysis": "先保证高频基础分，再逐步提升，符合及格优先的策略。",
            "knowledge_point": "高频计算与解题方法",
        },
        {
            "question": f"（Mock）下列关于{subject}复习计划的说法，最合理的是？",
            "options": ["A. 每天长时间只学一门", "B. 按计划分块复习并定期自测", "C. 考前一夜突击", "D. 只看笔记不做题"],
            "answer": "B",
            "analysis": "分块复习配合自测能及时发现薄弱点，效率最高。",
            "knowledge_point": "复习方法",
        },
    ]
    # 按画像裁剪：计划天数不超过 available_days，每天任务量不超过 daily_hours*60 分钟
    try:
        days = int(profile.available_days)
    except (TypeError, ValueError):
        days = None
    days = max(1, min(days or len(plan_titles), len(plan_titles)))
    try:
        hours = float(profile.daily_hours)
    except (TypeError, ValueError):
        hours = None
    minutes = int(min((hours or 3) * 60, 240))

    return {
        "course": subject,
        "summary": f"（Mock 数据）{subject}目标：{goal or '按当前学习画像复习'}。"
        f"{'加强综合应用与限时训练，' if strategy == 'high' else '先巩固核心概念与常见题型，'}"
        f"每天按计划推进并及时自测。生成内容仅供复习参考，请结合教材与课堂要求判断。",
        "knowledge_points": [
            {"name": n, "weight": w, "importance": i, "recommend_reason": r, "source": s, "suggest_hours": 6 - idx}
            for idx, (n, w, i, r, s) in enumerate(kp_templates)
        ],
        "exam_focus": [
            {"content": c, "level": l, "basis": b, "source": s, "frequency": f}
            for c, l, b, s, f in focus_templates
        ],
        "question_types": question_types,
        "review_plan": [
            {
                "day": i + 1,
                "date": (today + timedelta(days=i)).isoformat(),
                "title": f"（Mock）第{i + 1}天：{plan_titles[i]}",
                "estimated_minutes": minutes,
                "priority": 1 if i < 2 else 2,
                "detail": "结合资料中的重点内容复习，完成后做对应自测题。",
            }
            for i in range(days)
        ],
        "quiz": quiz_templates,
    }


# ==================== 资料问答（用例 4.5） ====================

QA_SYSTEM_PROMPT = """你是"期末周别慌"系统的资料问答助手。请只依据用户上传的复习资料回答问题。

要求：
1. 回答简洁、分点，优先引用资料中的原文，并说明出自哪份资料/哪类来源；
2. 资料没有覆盖的内容，直接说明「资料中未找到相关内容」，不要编造；
3. 可以结合之前的对话继续追问，但不要脱离资料范围；
4. 涉及考试结论时提醒学生结合教材与老师要求判断。"""


def build_qa_system_prompt(materials_text: str) -> str:
    return f"{QA_SYSTEM_PROMPT}\n\n【可参考资料】\n{materials_text}"


def mock_qa_answer(subject: str, question: str, materials_text: str) -> str:
    """Mock 资料问答：用问题中的 2~3 字片段匹配资料句子；找不到时明确说明"""
    stop_words = {
        "什么", "怎么", "如何", "为什么", "哪些", "一下", "可以", "这个", "那个",
        "资料", "请问", "帮我", "告诉我", "多少", "是否", "重要", "用来", "应该",
    }
    chunks = re.findall(r"[一-龥A-Za-z0-9]{2,}", question or "")
    grams = set()
    for chunk in chunks:
        for size in (2, 3):
            for index in range(len(chunk) - size + 1):
                gram = chunk[index : index + size]
                if gram not in stop_words:
                    grams.add(gram)

    sentences = [s.strip() for s in re.split(r"[。！？；\n]", materials_text or "") if s.strip()]
    scored = []
    for sentence in sentences:
        score = sum(1 for gram in grams if gram in sentence)
        if score:
            scored.append((score, sentence))
    scored.sort(key=lambda item: item[0], reverse=True)
    hits = [sentence for _, sentence in scored[:3]]

    if not hits:
        return (
            f"（Mock）在{subject}的资料中没有找到与「{question}」直接相关的内容。"
            "建议补充相关资料，或换个关键词再问。"
        )
    body = "\n".join(f"- {hit[:160]}" for hit in hits)
    return (
        f"（Mock）根据已上传的资料，与「{question}」相关的内容有：\n{body}\n\n"
        "以上内容仅供复习参考，请结合教材与老师要求判断。"
    )


# ==================== 备考周报（FMZH-SRS-5.3.0） ====================

WEEKLY_REPORT_SYSTEM_PROMPT = """你是"期末周别慌"系统的备考周报助手。请根据本周的任务完成率与专注时长，给各科目做掌握程度评测。

输出要求（严格 JSON，不要输出任何其他文字）：
{
  "summary": "本周整体总结，一两句话",
  "overall_mastery": 72,
  "highlights": ["本周值得肯定的地方", "..."],
  "next_week_advice": ["下周具体可执行的建议", "..."],
  "subjects": [
    {"subject": "高等数学", "mastery": 75, "level": "良好", "comment": "掌握情况简评", "suggestions": ["具体建议", "..."]}
  ]
}

约束：
1. mastery 为 0~100 的整数；level 只取 优秀（>=85）/ 良好（>=70）/ 一般（>=55）/ 薄弱（<55）。
2. 只评价输入 JSON 中出现的科目，不要编造科目；每个科目都必须给出评测。
3. 评分综合任务完成率、专注时长、距离考试天数判断；数据少时不要给出过高分，并在 comment 中说明依据有限。
4. suggestions 和 next_week_advice 要具体可执行（例如优先补哪类内容、每天投入多久），不要空泛。
5. 生成内容仅供复习参考，提示用户结合教材与课堂要求。"""


def build_weekly_report_user_prompt(week_start: str, week_end: str, metrics: list[dict]) -> str:
    return (
        f"统计区间：{week_start} ~ {week_end}\n"
        "本周各科数据（JSON；rate 为任务完成率，days_left 为距考试天数）：\n"
        f"{json.dumps(metrics, ensure_ascii=False, indent=2)}\n"
        "请按系统要求输出 JSON。"
    )


def _weekly_level(score: int) -> str:
    if score >= 85:
        return "优秀"
    if score >= 70:
        return "良好"
    if score >= 55:
        return "一般"
    return "薄弱"


def mock_subject_evaluation(metric: dict) -> dict:
    """Mock 单科评测：按完成率与专注时长给出稳定的掌握度评分"""
    subject = str(metric.get("subject") or "")
    minutes = int(metric.get("minutes") or 0)
    rate = float(metric.get("rate") or 0)
    done = int(metric.get("done_tasks") or 0)
    total = int(metric.get("total_tasks") or 0)

    # 40 分基础 + 完成率最多 45 分 + 专注投入最多 15 分
    score = int(round(40 + rate * 45 + min(minutes / 240, 1) * 15))
    score = max(0, min(100, score))
    level = _weekly_level(score)

    if rate >= 0.8 and minutes >= 180:
        comment = f"本周节奏稳定，完成率 {rate:.0%}，专注 {minutes} 分钟，基础掌握较扎实，可以开始挑战综合题。"
        suggestions = ["保持当前节奏，穿插综合题与易错点复盘，避免只做熟悉题型。"]
    elif rate >= 0.5:
        comment = f"本周完成率 {rate:.0%}，专注 {minutes} 分钟，进度基本可控，但仍有一定提升空间。"
        suggestions = ["把未完成任务拆成 30~45 分钟的小块，优先补齐高权重知识点。"]
    else:
        comment = f"本周完成率仅 {rate:.0%}，专注 {minutes} 分钟，推进偏慢，需要及时调整复习计划。"
        suggestions = [
            "先保证每天至少 1 个番茄钟，恢复稳定节奏。",
            "优先完成高优先级任务，避免任务堆积到考前。",
        ]

    try:
        days_left = int(metric.get("days_left"))
    except (TypeError, ValueError):
        days_left = None
    if days_left is not None and days_left <= 7:
        suggestions.append(f"距离考试仅剩 {days_left} 天，建议以真题和高频考点为主。")
    if total and done >= total:
        suggestions.append("本周任务已全部完成，可增加一次自测检验真实掌握程度。")

    return {
        "subject": subject,
        "mastery": score,
        "level": level,
        "comment": comment,
        "suggestions": suggestions[:3],
    }


def mock_generate_weekly_report(metrics: list[dict]) -> dict:
    """Mock 周报：汇总各科数据并生成掌握度评测与建议"""
    items = [mock_subject_evaluation(m) for m in metrics if m.get("subject")]
    scores = [item["mastery"] for item in items]
    overall = int(round(sum(scores) / len(scores))) if scores else None

    total_minutes = sum(int(m.get("minutes") or 0) for m in metrics)
    total_tasks = sum(int(m.get("total_tasks") or 0) for m in metrics)
    done_tasks = sum(int(m.get("done_tasks") or 0) for m in metrics)
    rate = done_tasks / total_tasks if total_tasks else 0.0

    summary = (
        f"（Mock）本周共学习 {total_minutes} 分钟，完成任务 {done_tasks}/{total_tasks}"
        f"（完成率 {rate:.0%}）。"
    )
    best = max(items, key=lambda x: x["mastery"]) if items else None
    weakest = min(items, key=lambda x: x["mastery"]) if items else None
    if best and weakest:
        if best["subject"] == weakest["subject"]:
            summary += f"{best['subject']}是本周主要复习科目，建议继续巩固并补充自测。"
        else:
            summary += (
                f"{best['subject']}掌握最好（{best['mastery']} 分），"
                f"{weakest['subject']}相对薄弱（{weakest['mastery']} 分），"
                "下周建议向后者适当倾斜时间。"
            )

    highlights = []
    if best:
        highlights.append(f"{best['subject']}掌握度最高：{best['mastery']} 分（{best['level']}）")
    if total_minutes:
        highlights.append(f"本周累计专注 {total_minutes} 分钟")
    if total_tasks:
        highlights.append(f"任务完成率 {rate:.0%}（{done_tasks}/{total_tasks}）")

    advice = []
    if weakest and weakest["mastery"] < 70:
        advice.append(f"{weakest['subject']}优先补薄弱章节，每天安排 1 个专项番茄钟。")
    advice.append("保持每天复盘 10 分钟，把错题与未完成任务及时清理。")
    advice.append("下周至少完成一次整卷或整套自测，检验真实掌握程度。")

    return {
        "summary": summary,
        "overall_mastery": overall,
        "highlights": highlights[:4],
        "next_week_advice": advice[:4],
        "subjects": items,
    }
