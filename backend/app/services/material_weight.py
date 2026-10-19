"""复习资料权重（用例 4.2 / README 3.1 两级权重体系）

资料权重衡量「资料可不可信」，按来源层级给默认值，学生可对单份资料手动调整；
与「知识点权重」（衡量知识点重不重要）是两套独立口径。

默认层级：老师标注重点 ＞ 历年试题/练习题 ＞ 平时作业/课堂笔记 ＞ 教材章节/实验报告
"""
DEFAULT_SOURCE_WEIGHT: dict[str, float] = {
    "老师重点": 1.0,
    "历年题": 0.85,
    "练习题": 0.85,
    "平时作业": 0.7,
    "课堂笔记": 0.7,
    "教材章节": 0.55,
    "实验报告": 0.55,
    "其他": 0.5,
}

# 未在层级表中出现的来源统一按最低档处理
DEFAULT_WEIGHT = 0.5


def default_weight_for(source_type: str) -> float:
    """按来源类型返回默认资料权重（0~1）"""
    return DEFAULT_SOURCE_WEIGHT.get(source_type, DEFAULT_WEIGHT)


def weight_level_for(weight: float) -> str:
    """权重档位（用例 3.2）：高 ≥0.85 / 中 ≥0.70 / 低 <0.70"""
    if weight >= 0.85:
        return "高"
    if weight >= 0.70:
        return "中"
    return "低"
