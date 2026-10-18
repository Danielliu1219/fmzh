"""客观题按服务端答案判分；未交卷不返回参考答案。"""
import json
import re
import unicodedata

from fastapi import HTTPException


def clean_text(value):
    return " ".join(unicodedata.normalize("NFKC", value).split())


def boolean_value(value):
    text = clean_text(value).lower()
    if text in ("true", "t", "正确", "对", "是", "√"):
        return "true"
    if text in ("false", "f", "错误", "错", "否", "×"):
        return "false"
    raise ValueError("判断题只能选择正确或错误")


def canonical_answer(question, value):
    kind = question["kind"]
    if value == "" or value == []:
        return ""
    if kind == "multiple":
        parts = value if isinstance(value, list) else re.split(r"[,，、;；\s]+", value.strip())
        if len(parts) == 1 and re.fullmatch(r"[A-Za-z]{2,}", parts[0]):
            parts = list(parts[0])
        keys = sorted(set(p.upper().strip() for p in parts if p.strip()))
        if not keys or any(k not in [o["value"] for o in question["options"]] for k in keys):
            raise ValueError("多选题包含无效选项")
        return keys
    if not isinstance(value, str):
        raise ValueError("此题需要单个答案")
    if kind == "single":
        text = clean_text(value)
        for option in question["options"]:
            if text.upper() == option["value"] or text == option["label"] or re.match(r"^" + option["value"] + r"[.、:：)）\s]", text.upper()):
                return option["value"]
        raise ValueError("单选题包含无效选项")
    if kind == "boolean":
        return boolean_value(value)
    return clean_text(value)


def prepare_questions(raw):
    if not isinstance(raw, list) or not 1 <= len(raw) <= 50:
        raise ValueError("没有可用自测题，请重新生成分析")
    prepared = []
    for i, item in enumerate(raw):
        options = item.get("options") or []
        answer = item.get("answer", "")
        kind = item.get("kind") or ("single" if options else "fill")
        if not item.get("kind") and not options:
            try:
                boolean_value(answer)
                kind = "boolean"
            except ValueError:
                pass
        if kind not in ("single", "multiple", "boolean", "fill"):
            raise ValueError(f"第 {i+1} 题类型不支持自动判分")
        if not isinstance(item.get("question"), str) or not item["question"].strip():
            raise ValueError(f"第 {i+1} 题缺少题干")
        if kind in ("single", "multiple") and not 2 <= len(options) <= 26:
            raise ValueError(f"第 {i+1} 题选项不完整")
        question = {
            "index": i, "kind": kind, "question": item["question"].strip(),
            "knowledge_point": item.get("knowledge_point", ""),
            "options": [{"value": chr(65+n), "label": re.sub(r"^[A-Z][.、:：)）]\s*", "", str(o))} for n, o in enumerate(options)] if kind in ("single", "multiple") else [],
            "analysis": item.get("analysis", ""),
        }
        question["answer"] = canonical_answer(question, answer)
        if not question["answer"]:
            raise ValueError(f"第 {i+1} 题参考答案为空")
        question["accepted_answers"] = [clean_text(a) for a in item.get("accepted_answers", []) if a.strip()] if kind == "fill" else []
        prepared.append(question)
    return prepared


def public_analysis(result):
    output = result.model_copy(deep=True)
    for question in output.quiz:
        question.answer = ""
        question.analysis = ""
        question.accepted_answers = []
    return output


def attempt_output(attempt):
    questions = json.loads(attempt.questions_json)
    return {
        "id": attempt.id, "analysis_id": attempt.analysis_id, "exam_id": attempt.exam_id,
        "subject": attempt.subject, "status": attempt.status,
        "created_at": attempt.created_at, "submitted_at": attempt.submitted_at,
        "questions": [{k: v for k, v in q.items() if k not in ("answer", "analysis", "accepted_answers")} for q in questions],
        "result": json.loads(attempt.result_json) if attempt.result_json else None,
    }


def grade_questions(questions, answers):
    if len(questions) != len(answers):
        raise HTTPException(422, "作答数量与题目数量不一致")
    normalized, items = [], []
    for question, answer in zip(questions, answers):
        try:
            answer = canonical_answer(question, answer)
        except ValueError as exc:
            raise HTTPException(422, f"第 {question['index']+1} 题：{exc}")
        normalized.append(answer)
        correct = answer != "" and (answer == question["answer"] or (question["kind"] == "fill" and answer in question["accepted_answers"]))
        items.append({**question, "submitted_answer": answer, "correct": correct, "unanswered": answer == "", "collection_id": None})
    total = len(items)
    correct = sum(i["correct"] for i in items)
    return normalized, {
        "score": round(correct / total * 100, 1), "total": total, "correct": correct,
        "wrong": total-correct, "unanswered": sum(i["unanswered"] for i in items),
        "mistakes_added": 0, "items": items,
    }
