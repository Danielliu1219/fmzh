"""四川大学现行本科成绩区间；保留旧 target 作为内部推荐策略。

教务处公开对照表：https://jwc.scu.edu.cn/info/1066/3444.htm
2017–2018 秋季学期起适用，D 档为 60 分及格线。
"""
from typing import Literal

ScoreBand = Literal["D", "D+", "C-", "C", "C+", "B-", "B", "B+", "A-", "A"]
SCORE_BANDS = {
    "D": (60, 60, "1.0"), "D+": (61, 62, "1.3"),
    "C-": (63, 65, "1.7"), "C": (66, 69, "2.0"),
    "C+": (70, 72, "2.3"), "B-": (73, 75, "2.7"),
    "B": (76, 79, "3.0"), "B+": (80, 84, "3.3"),
    "A-": (85, 89, "3.7"), "A": (90, 100, "4.0"),
}


def band_strategy(band):
    minimum = SCORE_BANDS[band][0]
    return "pass" if minimum < 70 else "medium" if minimum < 85 else "high"


def band_text(band):
    if band not in SCORE_BANDS:
        return ""
    minimum, maximum, gpa = SCORE_BANDS[band]
    label = "及格档（60 分及格线）" if minimum == maximum else f"{minimum}–{maximum} 分"
    return f"{label}，绩点 {gpa}（{band}）"
