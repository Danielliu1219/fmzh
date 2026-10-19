"""资料来源辅助识别（用例 3.2）

根据文件名与解析正文中的关键词，给出七类来源的识别建议，供学生确认。
识别只做「建议」，不替学生做最终选择；解析失败时仍可按文件名给建议。
"""
# 来源类型 -> 特征关键词。顺序仅用于同分时的兜底，不影响按分数取最高。
SOURCE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "实验报告": ("实验报告", "实验", "报告"),
    "老师重点": ("老师重点", "重点", "考点", "提纲", "讲义", "标注"),
    "历年题": ("历年", "真题", "考题", "试卷", "试题", "期末考"),
    "课堂笔记": ("课堂笔记", "笔记", "听课", "课堂记录"),
    "平时作业": ("平时作业", "作业", "课后作业", "homework"),
    "教材章节": ("教材", "课本", "章节", "课件", "ppt"),
    "练习题": ("练习题", "练习", "习题", "题库", "刷题", "exercise"),
}

# 文件名命中比正文命中更有区分度；正文最多累计 3 次，避免长文档刷分
FILENAME_HIT_SCORE = 6
CONTENT_HIT_SCORE = 1
MAX_CONTENT_HITS = 3
# 只扫描正文前 20000 字，避免大文件拖慢上传前建议
CONTENT_SCAN_LIMIT = 20000

HIGH_SCORE = 12
MEDIUM_SCORE = 6


def suggest_source(filename: str, text: str = "") -> dict:
    """返回 {"source_type", "confidence", "reason"}

    confidence 为 high / medium / low；没有命中任何特征时归为「其他」。
    """
    name = (filename or "").lower()
    body = (text or "")[:CONTENT_SCAN_LIMIT].lower()

    best_type = "其他"
    best_score = 0
    best_hits: list[str] = []

    for source_type, keywords in SOURCE_KEYWORDS.items():
        score = 0
        hits: list[str] = []
        for keyword in keywords:
            key = keyword.lower()
            if key in name:
                score += FILENAME_HIT_SCORE
                hits.append(f"文件名含「{keyword}」")
            count = body.count(key)
            if count:
                score += min(count, MAX_CONTENT_HITS) * CONTENT_HIT_SCORE
                hits.append(f"正文出现「{keyword}」{count} 次")
        if score > best_score:
            best_type, best_score, best_hits = source_type, score, hits

    if best_score == 0:
        return {
            "source_type": "其他",
            "confidence": "low",
            "reason": "未识别到明显的来源特征，默认归为「其他」，可手动选择",
        }

    confidence = "high" if best_score >= HIGH_SCORE else "medium" if best_score >= MEDIUM_SCORE else "low"
    return {
        "source_type": best_type,
        "confidence": confidence,
        "reason": "；".join(best_hits[:3]),
    }
