"""审查反例回归：真实临时SQLite事务、并发和文件，禁止访问用户数据。"""

import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from sqlalchemy.orm import Session
from app.models.models import (
    Analysis,
    FileCleanupJob,
    Material,
    Task,
    User,
    UserProfile,
)
from app.routers import ai, materials, focus, dashboard, study, tasks, features
from app.services import deletion
from app.services.schema_upgrade import upgrade_schema
import test_auth_quizzes as fixtures


class AuditFixTests(unittest.TestCase):
    register = fixtures.AuthQuizTests.register
    call = fixtures.AuthQuizTests.call

    def setUp(self):
        fixtures.AuthQuizTests.setUp(self)
        self.patches = [
            patch.object(module, "UPLOAD_DIR", self.root / "uploads")
            for module in (materials, deletion)
        ]
        for item in self.patches:
            item.start()
        for name, module in [
            ("materials", materials),
            ("focus", focus),
            ("study", study),
            ("tasks", tasks),
            ("features", features),
        ]:
            self.client.app.include_router(module.router, prefix="/api/" + name)
        self.client.app.include_router(dashboard.router, prefix="/api")

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        fixtures.AuthQuizTests.tearDown(self)

    def course(self, days=5):
        return self.call(
            "POST",
            "/exams",
            dict(
                subject="审查回归", exam_date=str(date.today() + timedelta(days=days))
            ),
        )["id"]

    def upload(self, exam_id=None):
        response = self.client.post(
            "/api/materials",
            headers=self.headers,
            files={"file": ("note.txt", "概念与典型计算题。".encode())},
            data={"title": "复习笔记", **({"exam_id": exam_id} if exam_id else {})},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_null_material_metadata_clears_safely_and_invalid_length_is_atomic(self):
        item = self.upload()
        response = self.call(
            "PUT", f"/materials/{item['id']}", {"tags": None, "description": None}
        )
        self.assertEqual((response["tags"], response["description"]), ("", ""))
        self.assertEqual(len(self.call("GET", "/materials")), 1)
        self.call("PUT", f"/materials/{item['id']}", {"tags": "x" * 101}, status=422)
        self.assertEqual(self.call("GET", f"/materials/{item['id']}")["tags"], "")

    def test_legacy_null_material_metadata_is_repaired_idempotently(self):
        item = self.upload()
        with Session(self.engine) as db:
            material = db.get(Material, item["id"])
            material.tags = None
            material.description = None
            db.commit()
        upgrade_schema(self.engine)
        with self.engine.begin() as conn:
            upgrade_schema(conn)
        self.assertEqual(self.call("GET", "/materials")[0]["tags"], "")

    def generation_state(self):
        with Session(self.engine) as db:
            return (
                [(r.id, r.result_json) for r in db.query(Analysis)],
                [
                    (r.id, r.title, r.estimated_minutes, r.plan_date)
                    for r in db.query(Task)
                ],
            )

    def test_incomplete_or_invalid_model_result_never_replaces_existing_plan(self):
        eid = self.course()
        self.upload(eid)
        with Session(self.engine) as db:
            db.add(
                UserProfile(
                    user_id=1,
                    exam_id=eid,
                    is_complete=True,
                    target="pass",
                    learning_status="weak",
                    available_days=5,
                    daily_hours=1,
                )
            )
            db.add(
                Task(
                    user_id=1,
                    exam_id=eid,
                    title="原有有效计划",
                    plan_date=date.today(),
                    estimated_minutes=30,
                    source="ai",
                )
            )
            db.commit()
        valid = dict(
            course="审查回归",
            summary="复习参考",
            knowledge_points=[dict(name="概念", weight=0.8)],
            review_plan=[
                dict(
                    day=1,
                    date=str(date.today()),
                    title="概念练习",
                    estimated_minutes=30,
                )
            ],
            quiz=[dict(kind="fill", question="1+1=?", answer="2")],
        )
        candidates = [
            {"quiz": valid["quiz"]},
            {**valid, "review_plan": []},
            {**valid, "knowledge_points": []},
            {**valid, "summary": ""},
            {**valid, "summary": " "},
            {**valid, "quiz": [dict(kind="fill", question="", answer="2")]},
            {**valid, "review_plan": [dict(day=1, date="invalid", title="错误")]},
            {
                **valid,
                "review_plan": [
                    dict(
                        day=1,
                        date=str(date.today()),
                        title="错误",
                        estimated_minutes=-1,
                    )
                ],
            },
        ]
        before = self.generation_state()
        for result in candidates:
            with (
                self.subTest(result=result),
                patch.object(ai.settings, "LLM_MOCK", False),
                patch.object(ai, "chat_json", return_value=result) as model,
            ):
                self.call("POST", "/ai/analyze", {"exam_id": eid}, status=502)
                self.assertEqual(model.call_count, 2)
                self.assertEqual(before, self.generation_state())
        with (
            patch.object(ai.settings, "LLM_MOCK", False),
            patch.object(ai, "chat_json", return_value=valid),
        ):
            self.assertTrue(
                self.call("POST", "/ai/analyze", {"exam_id": eid})["scheduling"][
                    "applied"
                ]
            )

    def test_deactivation_commit_failure_preserves_account_rows_and_files(self):
        item = self.upload()
        with Session(self.engine) as db:
            path = Path(db.get(Material, item["id"]).file_path)
        with patch.object(
            Session, "commit", side_effect=RuntimeError("database unavailable")
        ):
            self.assertEqual(
                self.client.delete("/api/auth/me", headers=self.headers).status_code,
                500,
            )
        self.assertTrue(path.is_file())
        self.assertEqual(len(self.call("GET", "/materials")), 1)
        with Session(self.engine) as db:
            self.assertIsNotNone(db.get(User, 1))
            self.assertEqual(db.query(FileCleanupJob).count(), 0)

    def test_deactivation_file_failure_keeps_durable_retry(self):
        item = self.upload()
        with Session(self.engine) as db:
            path = Path(db.get(Material, item["id"]).file_path)
        with patch.object(Path, "unlink", side_effect=PermissionError("file busy")):
            response = self.call("DELETE", "/auth/me")
        self.assertTrue(response["cleanup_pending"])
        self.assertTrue(path.is_file())
        with Session(self.engine) as db:
            self.assertIsNone(db.get(User, 1))
            self.assertEqual(db.query(Material).count(), 0)
            self.assertEqual(db.query(FileCleanupJob).count(), 1)
            self.assertEqual(deletion.retry_file_cleanup(db)["pending"], 0)
        self.assertFalse(path.exists())

    def test_reverse_schedule_cannot_exceed_shared_budget(self):
        eid = self.course()
        self.call("PUT", "/study/settings", {"daily_minutes": 60})
        result = self.call(
            "POST",
            f"/exams/{eid}/generate-schedule",
            {"daily_minutes": 600, "start_date": str(date.today())},
        )
        self.assertFalse(result["conflicts"])
        self.assertGreater(result["created"], 0)
        with Session(self.engine) as db:
            self.assertTrue(all(t.estimated_minutes <= 60 for t in db.query(Task)))

    def test_reverse_capacity_failure_preserves_original_tasks(self):
        eid = self.course(3)
        self.call("PUT", "/study/settings", {"daily_minutes": 60})
        with Session(self.engine) as db:
            profile = UserProfile(user_id=1, exam_id=eid)
            db.add(profile)
            db.flush()
            db.add(
                Analysis(
                    user_id=1,
                    exam_id=eid,
                    profile_id=profile.id,
                    result_json=json.dumps(
                        {"review_plan": [{"estimated_minutes": 600}]}
                    ),
                )
            )
            db.add(
                Task(
                    user_id=1,
                    exam_id=eid,
                    title="【倒推】原有安排",
                    plan_date=date.today(),
                    estimated_minutes=30,
                    source="ai",
                )
            )
            db.commit()
        before = self.generation_state()
        result = self.call(
            "POST",
            f"/exams/{eid}/generate-schedule",
            {"daily_minutes": 600, "start_date": str(date.today())},
        )
        self.assertEqual(result["created"], 0)
        self.assertTrue(result["conflicts"])
        self.assertEqual(before, self.generation_state())

    def test_three_concurrent_wrong_passwords_lock_account(self):
        def login(_):
            return self.client.post(
                "/api/auth/login",
                json={"username": "owner", "password": "wrong-password"},
            ).status_code

        with ThreadPoolExecutor(max_workers=3) as pool:
            statuses = list(pool.map(login, range(3)))
        self.assertEqual(sorted(statuses), [401, 401, 403])
        self.assertEqual(
            self.client.post(
                "/api/auth/login", json={"username": "owner", "password": "StudyQA123"}
            ).status_code,
            403,
        )
