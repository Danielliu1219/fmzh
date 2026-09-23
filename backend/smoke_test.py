# -*- coding: utf-8 -*-
"""后端全流程冒烟测试：注册 -> 考试 -> 上传资料 -> 画像 -> 补全 -> 分析 -> 任务 -> 打卡 -> 统计

用法：后端启动后执行  .venv/Scripts/python.exe smoke_test.py
"""
import io
import sys

import httpx

BASE = "http://127.0.0.1:8000"
client = httpx.Client(timeout=60)

ok_count = 0


def check(name, condition, extra=""):
    global ok_count
    if condition:
        ok_count += 1
        print(f"  [PASS] {name}")
    else:
        print(f"  [FAIL] {name} {extra}")
        sys.exit(1)


# 1. 注册
print("== 注册 ==")
r = client.post(
    f"{BASE}/api/auth/register",
    json={
        "username": "testuser",
        "password": "test123456",
        "nickname": "测试同学",
        "student_no": "20240001",
        "major": "计算机",
        "grade": "2024级",
    },
)
if r.status_code == 409:
    print("  [INFO] 账号已存在，改为登录")
    r = client.post(f"{BASE}/api/auth/login", json={"username": "testuser", "password": "test123456"})
check("注册/登录", r.status_code == 200, r.text)
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# 2. 个人信息
print("== 个人信息 ==")
r = client.get(f"{BASE}/api/auth/me", headers=headers)
check("GET /auth/me", r.status_code == 200 and r.json()["username"] == "testuser", r.text)

# 3. 录入考试
print("== 考试 ==")
r = client.post(
    f"{BASE}/api/exams",
    headers=headers,
    json={"subject": "高等数学", "exam_date": "2026-09-12", "location": "教三101", "duration_minutes": 120},
)
check("录入考试", r.status_code == 200, r.text)
exam_id = r.json()["id"]

r = client.get(f"{BASE}/api/exams", headers=headers)
check("考试列表", r.status_code == 200 and len(r.json()) >= 1, r.text)

# 4. 上传资料（TXT，UTF-8 与 GBK 各一份）
print("== 上传资料 ==")
txt_content = """第一章 极限与连续
重点：极限的定义、两个重要极限、等价无穷小替换。
第二章 导数与微分
重点：求导法则、隐函数求导、高阶导数。
历年题高频：洛必达法则求极限、导数应用（单调性、极值）。"""
r = client.post(
    f"{BASE}/api/materials",
    headers=headers,
    files={"file": ("高数笔记.txt", io.BytesIO(txt_content.encode("utf-8")), "text/plain")},
    data={"title": "高数笔记", "exam_id": str(exam_id), "source_type": "课堂笔记"},
)
check("上传 TXT", r.status_code == 200 and r.json()["parse_status"] == "done", r.text)
material_id = r.json()["id"]

r = client.post(
    f"{BASE}/api/materials",
    headers=headers,
    files={"file": ("历年题.txt", io.BytesIO(txt_content.encode("gbk")), "text/plain")},
    data={"title": "高数历年题", "exam_id": str(exam_id), "source_type": "历年题"},
)
check("上传 GBK 编码 TXT", r.status_code == 200 and r.json()["parse_status"] == "done", r.text)

r = client.get(f"{BASE}/api/materials?exam_id={exam_id}", headers=headers)
check("资料列表", r.status_code == 200 and len(r.json()) == 2, r.text)

r = client.get(f"{BASE}/api/materials/{material_id}", headers=headers)
check("资料详情含预览", r.status_code == 200 and "极限" in r.json()["text_preview"], r.text)

# 5. 画像提取（故意缺"剩余天数"和"每天时长"）
print("== AI 画像 ==")
r = client.post(
    f"{BASE}/api/ai/profile",
    headers=headers,
    json={"exam_id": exam_id, "raw_text": "我这门课基本没学，只想及格，极限和积分不太会"},
)
check("画像提取", r.status_code == 200, r.text)
profile = r.json()
check("识别目标=pass", profile["target"] == "pass", str(profile))
check("识别基础=weak", profile["learning_status"] == "weak", str(profile))
check("识别薄弱章节", "极限" in profile["weak_chapters"] or "积分" in profile["weak_chapters"], str(profile))
check("画像不完整", profile["is_complete"] is False and "available_days" in profile["missing_fields"], str(profile))

# 6. 补全缺失字段
print("== 画像补全 ==")
r = client.post(
    f"{BASE}/api/ai/profile",
    headers=headers,
    json={"exam_id": exam_id, "supplement": "还有5天考试，每天能学3小时"},
)
check("补全后画像完整", r.status_code == 200 and r.json()["is_complete"] is True, r.text)

# 7. 生成复习分析
print("== AI 分析 ==")
r = client.post(f"{BASE}/api/ai/analyze", headers=headers, json={"exam_id": exam_id})
check("生成分析", r.status_code == 200, r.text)
result = r.json()["result"]
check("含知识点权重", len(result["knowledge_points"]) >= 3, str(result))
check("含常考点", len(result["exam_focus"]) >= 2, str(result))
check("含复习计划", len(result["review_plan"]) >= 3, str(result))
check("含自测题", len(result["quiz"]) >= 2, str(result))

r = client.get(f"{BASE}/api/ai/analyses/{exam_id}", headers=headers)
check("查询最新分析", r.status_code == 200, r.text)

# 8. 任务与打卡
print("== 任务与打卡 ==")
r = client.get(f"{BASE}/api/tasks?exam_id={exam_id}", headers=headers)
check("计划生成任务", r.status_code == 200 and len(r.json()) >= 3, r.text)
task_id = r.json()[0]["id"]

r = client.post(f"{BASE}/api/tasks/{task_id}/checkin", headers=headers)
check("打卡", r.status_code == 200 and r.json()["is_done"] is True, r.text)

r = client.delete(f"{BASE}/api/tasks/{task_id}/checkin", headers=headers)
check("取消打卡", r.status_code == 200 and r.json()["is_done"] is False, r.text)

r = client.get(f"{BASE}/api/tasks/today", headers=headers)
check("今日待办", r.status_code == 200, r.text)

# 9. 首页与统计
print("== 首页与统计 ==")
r = client.get(f"{BASE}/api/dashboard", headers=headers)
check("首页聚合", r.status_code == 200 and len(r.json()["exams"]) >= 1, r.text)
dash = r.json()
check("倒计时正确（5天后）", dash["exams"][0]["days_left"] == 5, str(dash["exams"][0]))

r = client.get(f"{BASE}/api/stats/{exam_id}", headers=headers)
check("单科统计", r.status_code == 200 and r.json()["total_tasks"] >= 3, r.text)

# 10. 删除资料
print("== 删除 ==")
r = client.delete(f"{BASE}/api/materials/{material_id}", headers=headers)
check("删除资料", r.status_code == 200, r.text)

print(f"\n全部通过：{ok_count} 项检查")
