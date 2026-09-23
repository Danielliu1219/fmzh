# -*- coding: utf-8 -*-
"""演示数据种子脚本：把首页 Mock 展示的同一套数据种进数据库，保证全站数据统一

背景：前端 Dashboard 之前用 mock 数据展示（3 个今日任务 / 总进度 38% / 3 门考试），
与课程管理、复习资料、AI 分析页读到的真实数据库不一致。
本脚本把这套演示数据写入数据库，前端 USE_MOCK 改为 false 后，所有页面同源一致。

用法：cd backend && .venv/Scripts/python.exe seed_demo.py
    - 对数据库中的【每个用户】生成一套统一演示数据（含演示账号 demo / demo123456）
    - 会清空该用户原有的考试/资料/画像/分析/任务（演示数据重置脚本）
    - 考试日期 = 运行当天 + 5 / +11 / +14 天，任何时候重跑都是"新鲜"的演示数据
    - 数据构成：3 门考试、3 份资料、1 个完整画像、1 份分析结果、8 个任务（3 个已完成）
"""
import json
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import UPLOAD_DIR
from app.database import SessionLocal
from app.models.models import Analysis, Exam, Material, Task, User, UserProfile
from app.utils.security import hash_password

today = date.today()
fmt = "%Y-%m-%d"


def d(offset_days: int) -> date:
    return today + timedelta(days=offset_days)


def ds(offset_days: int) -> str:
    return d(offset_days).strftime(fmt)


# ---------- 演示数据定义 ----------

EXAMS = [
    {"subject": "高等数学", "offset": 5, "location": "教三 101", "duration_minutes": 120, "note": "闭卷"},
    {"subject": "大学英语", "offset": 11, "location": "外语楼 205", "duration_minutes": 120, "note": "闭卷"},
    {"subject": "数据结构", "offset": 14, "location": "信息楼 302", "duration_minutes": 90, "note": "开卷"},
]

MATERIALS = [
    {
        "exam_subject": "高等数学",
        "title": "高数期末复习笔记",
        "source_type": "课堂笔记",
        "file_name": "高数复习笔记.txt",
        "content": (
            "第一章 极限与连续\n"
            "重点：极限的定义与性质、两个重要极限、等价无穷小替换。\n"
            "常考题型：求极限（洛必达法则、等价无穷小、夹逼准则）。\n\n"
            "第二章 导数与微分\n"
            "重点：求导法则、隐函数求导、参数方程求导、高阶导数。\n"
            "常考题型：导数应用（单调性、极值、最值、凹凸性）。\n\n"
            "第三章 积分学\n"
            "重点：不定积分换元法与分部积分、定积分牛顿-莱布尼茨公式。\n"
            "常考题型：定积分计算、反常积分敛散性。\n\n"
            "第四章 中值定理\n"
            "重点：罗尔定理、拉格朗日中值定理、柯西中值定理的条件与结论。\n"
            "常考题型：证明存在性命题。"
        ),
    },
    {
        "exam_subject": "高等数学",
        "title": "历年真题精选（2019-2023）",
        "source_type": "历年题",
        "file_name": "高数历年真题精选.txt",
        "content": (
            "2019 年真题回顾\n"
            "1. 求极限 lim(x→0)(sin x - x)/x^3。（两个重要极限与泰勒展开）\n"
            "2. 讨论 y = x^3 - 3x 的单调区间与极值。（导数应用）\n"
            "3. 计算 ∫0^1 x·e^x dx。（分部积分）\n\n"
            "2021 年真题回顾\n"
            "1. 判断反常积分 ∫1^+∞ 1/x^p dx 的敛散性。\n"
            "2. 用拉格朗日中值定理证明不等式。\n\n"
            "2023 年真题回顾\n"
            "1. 求参数方程确定的函数二阶导数。\n"
            "2. 定积分应用：求平面图形面积。"
        ),
    },
    {
        "exam_subject": "大学英语",
        "title": "核心单词表 Unit 1-3",
        "source_type": "老师重点",
        "file_name": "核心单词表.txt",
        "content": (
            "Unit 1\n"
            "significant 重要的；approach 方法；emphasis 强调；derive 来源于。\n"
            "Unit 2\n"
            "evaluate 评估；assume 假设；available 可获得的；contrast 对比。\n"
            "Unit 3\n"
            "apparent 显然的；considerable 相当大的；procedure 程序；theory 理论。\n"
            "老师提醒：Unit 1-3 词汇为完形填空与阅读高频词，务必熟练拼写。"
        ),
    },
    {
        "exam_subject": "数据结构",
        "title": "数据结构复习提纲",
        "source_type": "课堂笔记",
        "file_name": "数据结构复习提纲.txt",
        "content": (
            "第一章 绪论\n"
            "重点：时间复杂度与空间复杂度的度量、算法的五个特性。\n\n"
            "第二章 线性表\n"
            "重点：顺序表与单链表的存储结构、插入删除的时间复杂度、逆置算法。\n"
            "常考题型：单链表逆置、合并两个有序链表。\n\n"
            "第三章 栈与队列\n"
            "重点：栈的后进先出特性、表达式求值、循环队列判空判满。\n"
            "常考题型：中缀转后缀、循环队列元素个数计算。\n\n"
            "第四章 树与二叉树\n"
            "重点：二叉树的遍历（先序/中序/后序/层序）、哈夫曼树、线索二叉树。\n"
            "常考题型：由遍历序列还原二叉树、计算叶子结点数。\n\n"
            "第五章 图\n"
            "重点：邻接矩阵与邻接表、深度/广度优先遍历、最小生成树、最短路径。\n\n"
            "第六章 查找与排序\n"
            "重点：二分查找、哈希表冲突处理、快排/堆排/归并排序的稳定性与复杂度。\n"
            "老师提醒：树和图是期末考试大题的主要来源。"
        ),
    },
]

# 高数画像：与首页 mock 一致（完整画像，AI 分析页可直接看到"已有分析"）
PROFILE = {
    "raw_text": "我这门课基础比较薄弱，目标是保及格，极限和积分不太会，还有五天考试，每天能学三小时，希望重点讲常考题型。",
    "target": "pass",
    "learning_status": "weak",
    "available_days": 5,
    "daily_hours": 3.0,
    "weak_chapters": ["极限与连续", "定积分"],
    "output_need": ["常考题型"],
}

# 高数分析结果：4 天计划（第 1 天两节课时），与下方任务一一对应
ANALYSIS_RESULT = {
    "course": "高等数学",
    "summary": (
        "你的基础偏弱、目标是保及格，所以策略是：先吃透极限与导数两大必考板块（占分约 60%），"
        "再用真题巩固；积分与中值定理掌握基础题型即可，空间解析几何战略性放弃。"
    ),
    "knowledge_points": [
        {"name": "极限与连续", "weight": 0.85, "importance": "high", "recommend_reason": "基础核心，历年必考，也是你的薄弱章节", "source": "老师重点", "suggest_hours": 4},
        {"name": "导数与微分", "weight": 0.75, "importance": "high", "recommend_reason": "与极限联动紧密，题型固定好拿分", "source": "课堂笔记", "suggest_hours": 3},
        {"name": "积分学", "weight": 0.6, "importance": "medium", "recommend_reason": "计算量大但套路固定，练熟基础题即可", "source": "历年题", "suggest_hours": 3},
        {"name": "中值定理", "weight": 0.45, "importance": "medium", "recommend_reason": "证明题偶尔出现，时间充裕再练", "source": "课堂笔记", "suggest_hours": 2},
        {"name": "空间解析几何", "weight": 0.25, "importance": "low", "recommend_reason": "分值低，时间紧可略过", "source": "历年题", "suggest_hours": 1},
    ],
    "exam_focus": [
        {"content": "两个重要极限与等价无穷小替换", "level": "must", "basis": "近五年每年必考，常以填空+计算出现", "source": "历年题"},
        {"content": "洛必达法则求极限", "level": "must", "basis": "高频题型，你目前不会，优先补", "source": "老师重点"},
        {"content": "中值定理证明", "level": "frequent", "basis": "隔年出现，时间充裕再练", "source": "课堂笔记"},
    ],
    "review_plan": [
        {"day": 1, "date": ds(0), "title": "核心概念与定义", "estimated_minutes": 90, "priority": 1, "detail": "极限定义、两个重要极限，配套 10 道基础题"},
        {"day": 2, "date": ds(1), "title": "高频题型刷题", "estimated_minutes": 120, "priority": 1, "detail": "洛必达法则与等价无穷小替换专项 15 题"},
        {"day": 3, "date": ds(2), "title": "导数应用专项", "estimated_minutes": 90, "priority": 2, "detail": "单调性、极值与最值题型 10 题"},
        {"day": 4, "date": ds(3), "title": "综合题与易错点", "estimated_minutes": 150, "priority": 3, "detail": "真题 3 套 + 错题回顾"},
    ],
    "quiz": [
        {
            "question": "设 f(x) 在 x→0 时与 sin x 是等价无穷小，则 lim(x→0) f(x)/x = ？",
            "options": ["0", "1", "-1", "不存在"],
            "answer": "1",
            "analysis": "等价无穷小替换：f(x) ~ sin x ~ x，故极限为 1。",
            "knowledge_point": "极限与连续",
        },
        {
            "question": "函数 y = x³ - 3x 的单调递增区间是？",
            "options": ["(-1, 1)", "(-∞, -1)∪(1, +∞)", "(-∞, +∞)", "(0, +∞)"],
            "answer": "(-∞, -1)∪(1, +∞)",
            "analysis": "y' = 3x² - 3 = 3(x-1)(x+1)，x < -1 或 x > 1 时 y' > 0。",
            "knowledge_point": "导数与微分",
        },
        {
            "question": "∫₀¹ x dx = ？",
            "options": ["0", "1/2", "1", "2"],
            "answer": "1/2",
            "analysis": "幂函数积分公式：∫x dx = x²/2。",
            "knowledge_point": "积分学",
        },
    ],
}

# 8 个任务：4 个 AI 计划任务 + 4 个手动任务；3 个已完成 → 总进度 38%
# 今日 3 个任务（1 完成）→ 首页"今日任务 1/3"，与 mock 展示一致
TASKS = [
    # —— AI 任务（来自高数 4 天计划）——
    {"exam_subject": "高等数学", "title": "核心概念与定义", "offset": 0, "minutes": 90, "priority": 1, "done": True, "source": "ai"},
    {"exam_subject": "高等数学", "title": "高频题型刷题", "offset": 1, "minutes": 120, "priority": 1, "done": False, "source": "ai"},
    {"exam_subject": "高等数学", "title": "导数应用专项", "offset": 2, "minutes": 90, "priority": 2, "done": False, "source": "ai"},
    {"exam_subject": "高等数学", "title": "综合题与易错点", "offset": 3, "minutes": 150, "priority": 3, "done": False, "source": "ai"},
    # —— 手动任务 ——
    {"exam_subject": "高等数学", "title": "极限与连续薄弱专项", "offset": 0, "minutes": 120, "priority": 1, "done": False, "source": "manual"},
    {"exam_subject": "高等数学", "title": "摸底自测", "offset": -1, "minutes": 60, "priority": 1, "done": True, "source": "manual"},
    {"exam_subject": "大学英语", "title": "单词 Unit 1-3 记忆", "offset": 0, "minutes": 45, "priority": 2, "done": False, "source": "manual"},
    {"exam_subject": "大学英语", "title": "听力精听 30 分钟", "offset": -1, "minutes": 30, "priority": 3, "done": True, "source": "manual"},
]


def seed() -> None:
    db = SessionLocal()

    # 演示账号：始终存在，密码固定 demo123456
    demo = db.query(User).filter(User.username == "demo").first()
    if not demo:
        demo = User(
            username="demo",
            hashed_password=hash_password("demo123456"),
            nickname="演示同学",
            student_no="20240000",
            major="计算机",
            grade="2024级",
        )
        db.add(demo)
        db.flush()
    else:
        demo.hashed_password = hash_password("demo123456")
        demo.nickname = demo.nickname or "演示同学"
    users = db.query(User).all()

    # 演示资料文件落盘（保证删除资料时文件存在）
    demo_dir = UPLOAD_DIR / "demo"
    demo_dir.mkdir(parents=True, exist_ok=True)
    for m in MATERIALS:
        (demo_dir / m["file_name"]).write_text(m["content"], encoding="utf-8")

    for user in users:
        # 清空该用户旧数据（先删子表再删考试）
        db.query(Material).filter(Material.user_id == user.id).delete()
        db.query(UserProfile).filter(UserProfile.user_id == user.id).delete()
        db.query(Analysis).filter(Analysis.user_id == user.id).delete()
        db.query(Task).filter(Task.user_id == user.id).delete()
        db.query(Exam).filter(Exam.user_id == user.id).delete()

        # 1. 三门考试
        exam_map = {}
        for e in EXAMS:
            exam = Exam(
                user_id=user.id,
                subject=e["subject"],
                exam_date=d(e["offset"]),
                location=e["location"],
                duration_minutes=e["duration_minutes"],
                note=e["note"],
            )
            db.add(exam)
            db.flush()
            exam_map[e["subject"]] = exam

        # 2. 三份资料
        for m in MATERIALS:
            db.add(
                Material(
                    user_id=user.id,
                    exam_id=exam_map[m["exam_subject"]].id,
                    title=m["title"],
                    source_type=m["source_type"],
                    file_path=str(demo_dir / m["file_name"]),
                    file_type="txt",
                    text_content=m["content"],
                    parse_status="done",
                    description="演示数据（seed_demo.py 生成）",
                )
            )

        # 3. 高数画像（完整）与分析结果
        profile = UserProfile(
            user_id=user.id,
            exam_id=exam_map["高等数学"].id,
            raw_text=PROFILE["raw_text"],
            target=PROFILE["target"],
            learning_status=PROFILE["learning_status"],
            available_days=PROFILE["available_days"],
            daily_hours=PROFILE["daily_hours"],
            weak_chapters=json.dumps(PROFILE["weak_chapters"], ensure_ascii=False),
            output_need=json.dumps(PROFILE["output_need"], ensure_ascii=False),
            is_complete=True,
            missing_fields=json.dumps([], ensure_ascii=False),
        )
        db.add(profile)
        db.flush()
        analysis = Analysis(
            user_id=user.id,
            exam_id=exam_map["高等数学"].id,
            profile_id=profile.id,
            result_json=json.dumps(ANALYSIS_RESULT, ensure_ascii=False),
            status="success",
        )
        db.add(analysis)
        db.flush()

        # 4. 八个任务（与计划一致）
        for i, t in enumerate(TASKS):
            db.add(
                Task(
                    user_id=user.id,
                    exam_id=exam_map[t["exam_subject"]].id,
                    analysis_id=analysis.id if t["source"] == "ai" else None,
                    title=t["title"],
                    plan_date=d(t["offset"]),
                    estimated_minutes=t["minutes"],
                    priority=t["priority"],
                    sort_order=i,
                    is_done=t["done"],
                    done_at=datetime.now() if t["done"] else None,
                    source=t["source"],
                )
            )

    db.commit()
    usernames = "、".join(u.username for u in users)
    print(f"[OK] 已为 {len(users)} 个账号种入演示数据：{usernames}")
    print(f"     演示账号：demo / demo123456")
    print(f"     考试日期：高数 {ds(5)} · 英语 {ds(11)} · 数据结构 {ds(14)}")
    print(f"     任务 8 个（已完成 3 → 总进度 38%），今日任务 3 个（1 完成）")
    db.close()


if __name__ == "__main__":
    seed()
