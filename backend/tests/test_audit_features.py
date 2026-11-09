"""需求缺口回归：隔离数据库、真实事务和后台任务，不调用付费模型。"""

import io
import json
import time
import unittest
import zipfile
from datetime import date, datetime, time as clock, timedelta
from threading import Event
from threading import Barrier
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from sqlalchemy.orm import Session, sessionmaker
from fastapi.testclient import TestClient
from fastapi import HTTPException
from PIL import Image
from pptx import Presentation
from app.models.models import (
    Analysis,
    FocusSession,
    Material,
    OperationLog,
    Task,
    User,
    UserProfile,
    AIJob,
)
from app.routers import admin, ai, jobs, materials
from app.services import ai_jobs, material_parsing, model_usage, pressure
from app.services.audit import AuditMiddleware
from app.services.mood_advice import advice, RHYTHM, PLANS, SUPPORT
from app.services.schema_upgrade import upgrade_schema
from app.services.upload_guard import check_content_head, UploadRejected
import test_audit_fixes as fixes


class AuditFeatureTests(unittest.TestCase):
    register = fixes.AuditFixTests.register
    call = fixes.AuditFixTests.call
    course = fixes.AuditFixTests.course
    upload = fixes.AuditFixTests.upload
    setUp = fixes.AuditFixTests.setUp

    def tearDown(self):
        ai_jobs.stop()
        material_parsing.stop()
        fixes.AuditFixTests.tearDown(self)

    def test_student_number_unique_on_register_and_edit(self):
        self.call(
            "POST",
            "/auth/register",
            dict(username="duplicate", password="StudyQA123", student_no=" 20240001 "),
            status=409,
        )
        other = self.register("other")
        headers = {"Authorization": "Bearer " + other["access_token"]}
        self.call(
            "PUT", "/auth/me", dict(student_no="20240001"), headers=headers, status=409
        )
        self.assertEqual(
            self.call("GET", "/auth/me", headers=headers)["student_no"],
            "20240001_other",
        )
        self.call("PUT", "/auth/me", dict(student_no=""), headers=headers)
        self.call(
            "POST",
            "/auth/register",
            dict(username="blank", password="StudyQA123", student_no=""),
        )
        upgrade_schema(self.engine)
        upgrade_schema(self.engine)

    def test_exam_validation_time_and_calendar(self):
        base = dict(subject="数学", exam_date=str(date.today() + timedelta(days=3)))
        for change in [
            dict(subject=" "),
            dict(subject="x" * 65),
            dict(duration_minutes=-1),
            dict(duration_minutes=301),
            dict(exam_time="12:30:01"),
        ]:
            self.call("POST", "/exams", {**base, **change}, status=422)
        item = self.call("POST", "/exams", {**base, "exam_time": "14:30"})
        self.assertEqual(item["exam_time"], "14:30")
        self.call("PUT", f"/exams/{item['id']}", {"duration_minutes": None}, status=422)
        self.assertIn(
            "T063000Z",
            self.client.get("/api/exams/export-ics", headers=self.headers).text,
        )

    def test_focus_idempotency_conflicting_key_and_overlapping_interval(self):
        eid = self.course()
        end = datetime.now() - timedelta(minutes=30)
        data = dict(
            exam_id=eid,
            duration_minutes=30,
            start_time=str(end - timedelta(minutes=30)),
            end_time=str(end),
            request_id="repeat-focus",
        )
        first = self.call("POST", "/focus/sessions", data)
        self.assertEqual(first["id"], self.call("POST", "/focus/sessions", data)["id"])
        self.assertEqual(
            first["id"],
            self.call("POST", "/focus/sessions", {**data, "request_id": "second-key"})[
                "id"
            ],
        )
        self.call(
            "POST", "/focus/sessions", {**data, "duration_minutes": 31}, status=409
        )
        self.call(
            "POST",
            "/focus/sessions",
            {
                **data,
                "request_id": "third-key",
                "start_time": str(end - timedelta(minutes=20)),
                "end_time": str(end + timedelta(minutes=10)),
            },
            status=409,
        )
        with Session(self.engine) as db:
            self.assertEqual(db.query(FocusSession).count(), 1)

    def test_legacy_duplicate_focus_and_cross_midnight_statistics(self):
        midnight = datetime.combine(date.today(), clock.min)
        with Session(self.engine) as db:
            for _ in range(2):
                db.add(
                    FocusSession(
                        user_id=1,
                        start_time=midnight - timedelta(minutes=30),
                        end_time=midnight + timedelta(minutes=30),
                        duration_minutes=60,
                    )
                )
            db.add(
                FocusSession(
                    user_id=1,
                    start_time=midnight + timedelta(minutes=20),
                    end_time=midnight + timedelta(minutes=40),
                    duration_minutes=20,
                )
            )
            db.commit()
        self.assertEqual(self.call("GET", "/focus/today")["total_minutes"], 40)
        stats = self.call("GET", "/stats/overview?days=2")
        self.assertEqual(stats["total_minutes"], 70)
        self.assertEqual([d["minutes"] for d in stats["days"]], [30, 40])

    def test_pressure_threshold_uses_raw_value_not_rounded_display(self):
        with (
            patch.object(pressure, "_exam_density", return_value=0),
            patch.object(pressure, "_task_rates", return_value=(0, 0)),
            patch.object(pressure, "_exam_proximity", return_value=1.9999),
        ):
            result = pressure.calculate([], [], date.today())
        self.assertEqual(result["score"], 60)
        self.assertLess(result["raw_score"], 60)
        self.assertFalse(result["need_emergency"])

    def test_mood_raw_boundary_and_three_consecutive_low_days(self):
        today = date.today()
        previous = {today - timedelta(days=i): 2.499 for i in (1, 2)}
        result = advice(2.4999, today, 1, previous)
        self.assertEqual(result["low_days"], 3)
        self.assertTrue(result["need_emergency"])
        self.assertEqual(advice(2.5, today, 1, previous)["low_days"], 0)
        self.assertEqual((len(RHYTHM), len(PLANS), len(SUPPORT)), (10, 4, 8))
        self.assertEqual(
            advice(2.4, today, 1, {today - timedelta(days=2): 1})["low_days"], 1
        )

    def test_review_collects_only_own_course_and_separates_unassigned_questions(self):
        eid = self.course()
        other = self.course()
        item = self.upload(eid)
        self.call(
            "POST",
            "/collections",
            dict(item_type="material", material_id=item["id"]),
            status=201,
        )
        for title, scope in [
            ("本科错题", eid),
            ("另一科题", other),
            ("未分类题", None),
        ]:
            self.call(
                "POST",
                "/collections",
                dict(
                    item_type="question",
                    title=title,
                    content=json.dumps({"exam_id": scope, "answer": "42"}),
                ),
                status=201,
            )
        result = self.call("GET", f"/features/review?exam_id={eid}")
        names = [i["name"] for i in result["items"]]
        self.assertIn("本科错题", names)
        self.assertIn(item["title"], names)
        self.assertNotIn("另一科题", names)
        self.assertEqual([i["name"] for i in result["unassigned"]], ["未分类题"])

    def test_top_three_respects_analysis_knowledge_weight(self):
        eid = self.course()
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
                        {
                            "knowledge_points": [
                                {"name": "基础", "weight": 0.1},
                                {"name": "重点", "weight": 0.9},
                            ]
                        }
                    ),
                )
            )
            for point in ("基础", "重点"):
                db.add(
                    Task(
                        user_id=1,
                        exam_id=eid,
                        title=point,
                        knowledge_point=point,
                        priority=2,
                        plan_date=date.today(),
                        estimated_minutes=30,
                    )
                )
            db.commit()
        items = self.call("GET", "/features/top3")["items"]
        self.assertEqual(items[0]["title"], "重点")
        self.assertIn("知识点权重", items[0]["reason"])

    def test_custom_recurrence_sorts_deduplicates_and_rejects_out_of_range_atomically(
        self,
    ):
        eid = self.course(10)
        start = date.today()
        payload = dict(
            exam_id=eid,
            title="自选日期复习",
            plan_date=str(start),
            estimated_minutes=20,
            repeat_rule="custom",
            repeat_dates=[str(start + timedelta(days=3)), str(start), str(start)],
        )
        result = self.call("POST", "/tasks", payload)
        self.assertEqual(result["created_count"], 2)
        before = self.call("GET", "/tasks")
        self.call(
            "POST",
            "/tasks",
            {**payload, "repeat_dates": [str(start + timedelta(days=11))]},
            status=422,
        )
        self.assertEqual(self.call("GET", "/tasks"), before)

    def test_course_status_color_and_field_validation(self):
        self.client.app.include_router(admin.router, prefix="/api/admin")
        with Session(self.engine) as db:
            db.get(User, 1).is_admin = True
            db.commit()
        item = self.call(
            "POST",
            "/admin/courses",
            dict(name="课程", color="#123456", is_active=False),
        )
        self.assertFalse(item["is_active"])
        self.assertEqual(item["color"], "#123456")
        self.call("POST", "/admin/courses", dict(name=" ", credit=-1), status=422)
        item = self.call("PUT", f"/admin/courses/{item['id']}", dict(is_active=True))
        self.assertTrue(item["is_active"])

    def test_disabled_course_cannot_be_selected_and_color_is_inherited(self):
        self.client.app.include_router(admin.router, prefix="/api/admin")
        with Session(self.engine) as db:
            db.get(User, 1).is_admin = True
            db.commit()
        course = self.call(
            "POST", "/admin/courses", dict(name="统一科目", color="#123456")
        )
        exam = self.call(
            "POST",
            "/exams",
            dict(subject="统一科目", exam_date=str(date.today() + timedelta(days=3))),
        )
        self.assertEqual(exam["color"], "#123456")
        self.call("PUT", f"/admin/courses/{course['id']}", dict(is_active=False))
        self.assertEqual(self.call("GET", "/exams/course-options"), [])
        self.call(
            "POST",
            "/exams",
            dict(subject="统一科目", exam_date=str(date.today() + timedelta(days=4))),
            status=409,
        )
        self.call("PUT", f"/exams/{exam['id']}", dict(note="已有安排继续可维护"))

    def test_weekly_completion_uses_actual_checkin_date_and_preserves_unknown_history(
        self,
    ):
        eid = self.course()
        today = date.today()
        now = datetime.combine(today, clock(12))
        with Session(self.engine) as db:
            for title, planned, completed in [
                ("跨周补做", today - timedelta(days=10), now),
                ("早已完成", today, now - timedelta(days=10)),
                ("昨天计划今天做", today - timedelta(days=1), now),
                ("旧记录无时刻", today, None),
            ]:
                db.add(
                    Task(
                        user_id=1,
                        exam_id=eid,
                        title=title,
                        plan_date=planned,
                        is_done=True,
                        done_at=completed,
                        estimated_minutes=20,
                    )
                )
            db.commit()
        report = self.call("POST", "/reports/weekly", {})
        self.assertEqual(
            (report["total_tasks"], report["done_tasks"], report["rate"]), (4, 2, 0.5)
        )
        self.assertEqual(report["days"][-1]["done"], 2)
        self.assertEqual(sum(d["total"] for d in report["days"]), 4)
        self.assertIn("无完成时刻", report["note"])
        self.assertEqual(self.call("GET", "/stats/overview")["days"][-1]["done"], 2)

    def test_office_package_and_image_validation(self):
        fake = io.BytesIO()
        with zipfile.ZipFile(fake, "w") as archive:
            archive.writestr("note.txt", "not a word document")
        with self.assertRaises(UploadRejected):
            check_content_head(fake.getvalue(), "docx")
        image = io.BytesIO()
        Image.new("RGB", (20, 20)).save(image, format="PNG")
        check_content_head(image.getvalue(), "png")
        with self.assertRaises(UploadRejected):
            check_content_head(b"\x89PNG\r\n\x1a\ninvalid", "png")

    def test_storage_quota_is_atomic_and_visible(self):
        item = self.upload()
        with Session(self.engine) as db:
            db.get(Material, item["id"]).file_size = 1024 * 1024
            db.commit()
        with patch.object(materials.settings, "USER_STORAGE_LIMIT_MB", 1):
            self.assertEqual(
                self.call("GET", "/materials/storage")["remaining_bytes"], 0
            )
            response = self.client.post(
                "/api/materials",
                headers=self.headers,
                files={"file": ("note.txt", b"x")},
                data={"title": "excess"},
            )
            self.assertEqual(response.status_code, 413)
        self.assertEqual(len(self.call("GET", "/materials")), 1)

    def test_filename_fallback_cannot_bypass_material_title_limit_or_leave_a_file(self):
        response=self.client.post('/api/materials',headers=self.headers,
            data={'title':' '},files={'file':('a'*129+'.txt',b'notes')})
        self.assertEqual(response.status_code,422,response.text)
        self.assertEqual(self.call('GET','/materials'),[])
        self.assertEqual(list((self.root/'uploads').rglob('*.txt')),[])

    def test_background_pptx_parsing_failure_retry_and_request_id(self):
        presentation = Presentation()
        slide = presentation.slides.add_slide(presentation.slide_layouts[1])
        slide.shapes.title.text = "真实课件"
        data = io.BytesIO()
        presentation.save(data)
        with patch.object(material_parsing, "enqueue"):
            response = self.client.post(
                "/api/materials",
                headers=self.headers,
                files={"file": ("slides.pptx", data.getvalue())},
                data={"title": "课件"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        mid = response.json()["id"]
        self.assertEqual(response.json()["parse_status"], "pending")
        factory = sessionmaker(bind=self.engine)
        material_parsing.parse(factory, mid, self.root / "uploads", "trace-test")
        with Session(self.engine) as db:
            self.assertIn("真实课件", db.get(Material, mid).text_content)
            self.assertEqual(
                db.query(OperationLog)
                .filter_by(action="material.parse")
                .one()
                .request_id,
                "trace-test",
            )
        with patch.object(material_parsing, "enqueue"):
            self.call("POST", f"/materials/{mid}/retry")
        with patch.object(
            material_parsing, "parse_document", side_effect=ValueError("bad file")
        ):
            material_parsing.parse(factory, mid, self.root / "uploads")
        item = self.call("GET", f"/materials/{mid}")
        self.assertEqual(item["parse_status"], "failed")
        self.assertTrue(item["parse_error"])
        self.assertIn("上次成功解析", item["parse_error"])
        self.assertIn("真实课件", item["text_preview"])

    def test_pending_parse_can_be_recovered_and_duplicate_enqueue_is_ignored(self):
        item = self.upload()
        with Session(self.engine) as db:
            row = db.get(Material, item["id"])
            row.parse_status = "pending"
            db.commit()
        with patch.object(material_parsing, "enqueue") as enqueue:
            result = self.call("POST", f"/materials/{item['id']}/retry")
            self.assertEqual(result["parse_status"], "pending")
            enqueue.assert_called_once()
        started = Event()
        release = Event()

        def slow(*args):
            started.set()
            release.wait(5)

        factory = sessionmaker(bind=self.engine)
        with patch.object(material_parsing, "parse", side_effect=slow) as worker:
            self.assertTrue(
                material_parsing.enqueue(factory, item["id"], self.root / "uploads")
            )
            self.assertTrue(started.wait(2))
            self.assertFalse(
                material_parsing.enqueue(factory, item["id"], self.root / "uploads")
            )
            release.set()
            material_parsing.stop()
            self.assertEqual(worker.call_count, 1)

    def test_model_usage_is_persistent_user_scoped_and_unlimited(self):
        other = self.register("other")
        with Session(self.engine) as db:
            owner = db.get(User, 1)

            @model_usage.metered
            def invoke(*, user, db):
                model_usage.reserve_call()

            invoke(user=owner, db=db)
            invoke(user=owner, db=db)
            invoke(user=db.get(User, other["user"]["id"]), db=db)
            self.assertEqual(model_usage.limits(db, 1)["used_calls"], 2)
            self.assertIsNone(model_usage.limits(db, 1)["daily_limit"])
            self.assertIsNone(model_usage.limits(db, 1)["remaining_calls"])

    def test_concurrent_model_calls_are_counted_without_a_daily_limit(self):
        @model_usage.metered
        def reserve(*, user, db):
            model_usage.reserve_call()

        def invoke(_):
            with Session(self.engine) as db:
                try:
                    reserve(user=db.get(User, 1), db=db)
                    return 200
                except HTTPException as error:
                    return error.status_code

        with ThreadPoolExecutor(max_workers=8) as pool:
            statuses = list(pool.map(invoke, range(8)))
        self.assertEqual(statuses, [200] * 8)
        with Session(self.engine) as db:
            self.assertEqual(model_usage.limits(db, 1)["used_calls"], 8)

    def test_weekly_report_reads_saved_snapshot_without_generating_or_changing_it(self):
        self.assertIsNone(self.call('GET', '/reports/weekly'))
        report = self.call('POST', '/reports/weekly', {})
        with Session(self.engine) as db:
            db.add(AIJob(user_id=1, auth_key='', request_key='weekly-snapshot', kind='weekly',
                payload_json='{}', payload_hash='snapshot', status='succeeded',
                result_json=json.dumps(report), finished_at=datetime.now()))
            db.commit()
        with patch('app.routers.dashboard.chat_json') as generate:
            for _ in range(3):
                self.assertEqual(self.call('GET', '/reports/weekly'), report)
            self.assertEqual(self.call('GET', '/reports/weekly?week_start=' + report['week_start']), report)
            self.assertIsNone(self.call('GET', '/reports/weekly?week_start=2020-01-01'))
            generate.assert_not_called()
        other = self.register('weekly_other')
        self.assertIsNone(self.call('GET', '/reports/weekly', headers={'Authorization': 'Bearer ' + other['access_token']}))

    def test_failed_or_invalid_weekly_refresh_preserves_last_successful_snapshot(self):
        report = self.call('POST', '/reports/weekly', {})
        with Session(self.engine) as db:
            for key, status, result in [('saved', 'succeeded', json.dumps(report)),
                                        ('failed', 'failed', None), ('invalid', 'succeeded', '{}')]:
                db.add(AIJob(user_id=1, auth_key='', request_key=key, kind='weekly', payload_json='{}',
                    payload_hash=key, status=status, result_json=result, finished_at=datetime.now()))
            db.commit()
        self.assertEqual(self.call('GET', '/reports/weekly'), report)

    def test_async_job_fast_acceptance_idempotency_scope_and_completed_result(self):
        self.client.app.include_router(jobs.router, prefix="/api/ai")
        eid = self.course()
        release = Event()
        started = Event()

        def slow(payload, *, user, db):
            db.rollback()
            started.set()
            release.wait(5)
            return {"exam_id": eid, "is_complete": False}

        with patch.object(ai, "create_profile", side_effect=slow) as model:
            t = time.perf_counter()
            data = dict(
                kind="profile",
                request_key="idempotent-job",
                payload=dict(exam_id=eid, raw_text="学习情况"),
            )
            job = self.call("POST", "/ai/jobs", data, status=202)
            self.assertLess(time.perf_counter() - t, 2)
            self.assertTrue(started.wait(2))
            self.assertEqual(
                self.call("POST", "/ai/jobs", data, status=202)["id"], job["id"]
            )
            self.call(
                "POST",
                "/ai/jobs",
                {**data, "payload": dict(exam_id=eid, raw_text="不同内容")},
                status=409,
            )
            self.call("GET", "/exams")
            other = self.register("other")
            self.call(
                "GET",
                "/ai/jobs/" + job["id"],
                headers={"Authorization": "Bearer " + other["access_token"]},
                status=404,
            )
            release.set()
            ai_jobs.stop()
            result = self.call("GET", "/ai/jobs/" + job["id"])
            self.assertEqual(result["status"], "succeeded", result)
            self.assertEqual(result["result"]["exam_id"], eid)
            self.assertEqual(model.call_count, 1)

    def test_restart_marks_jobs_interrupted_without_paid_replay(self):
        with Session(self.engine) as db:
            job = AIJob(
                user_id=1,
                auth_key="secret",
                kind="profile",
                request_key="restart",
                payload_hash="x",
                payload_json='{"private":"input"}',
            )
            db.add(job)
            db.commit()
            jid = job.id
        ai_jobs.recover(sessionmaker(bind=self.engine))
        with Session(self.engine) as db:
            job = db.get(AIJob, jid)
            self.assertEqual(job.status, "failed")
            self.assertEqual(job.error_status, 409)
            self.assertEqual(job.payload_json, "{}")
            self.assertEqual(job.auth_key, "")

    def test_queued_model_job_cannot_target_a_replacement_with_reused_exam_id(self):
        self.client.app.include_router(jobs.router, prefix="/api/ai")
        eid = self.course()
        with patch.object(ai_jobs, "enqueue"):
            job = self.call(
                "POST",
                "/ai/jobs",
                dict(
                    kind="profile",
                    request_key="old-exam-job",
                    payload=dict(exam_id=eid, raw_text="旧考试描述"),
                ),
                status=202,
            )
        self.call("DELETE", f"/exams/{eid}")
        new = self.course()
        self.assertEqual(new, eid)  # 真实SQLite默认ROWID会复用已删除的最高编号。
        with patch.object(ai, "create_profile") as model:
            ai_jobs.execute(sessionmaker(bind=self.engine), job["id"])
            model.assert_not_called()
        result = self.call("GET", "/ai/jobs/" + job["id"])
        self.assertEqual((result["status"], result["error_status"]), ("failed", 409))

    def test_deleted_exam_questions_remain_archived_after_exam_id_reuse(self):
        eid = self.course()
        item = self.call(
            "POST",
            "/collections",
            dict(
                item_type="question",
                title="旧课错题",
                content=json.dumps({"exam_id": eid, "answer": "42"}),
            ),
            status=201,
        )
        self.call("DELETE", f"/exams/{eid}")
        new = self.course()
        self.assertEqual(new, eid)
        result = self.call("GET", f"/features/review?exam_id={new}")
        self.assertNotIn("旧课错题", [item["name"] for item in result["items"]])
        self.assertEqual(result["unassigned"][0]["collection_id"], item["id"])
        self.assertIn("考试已删除", result["unassigned"][0]["source"])

    def test_one_deduplicated_wrong_question_can_be_reviewed_in_each_actual_course(
        self,
    ):
        ids = [self.course(), self.course()]
        for eid in ids:
            with Session(self.engine) as db:
                profile = UserProfile(user_id=1, exam_id=eid)
                db.add(profile)
                db.flush()
                analysis = Analysis(
                    user_id=1,
                    exam_id=eid,
                    profile_id=profile.id,
                    result_json=json.dumps(
                        {
                            "quiz": [
                                dict(kind="fill", question="共同概念练习", answer="42")
                            ]
                        }
                    ),
                )
                db.add(analysis)
                db.commit()
                aid = analysis.id
            attempt = self.call("POST", "/quizzes", dict(analysis_id=aid), status=201)
            self.call(
                "POST", f"/quizzes/{attempt['id']}/submit", dict(answers=["wrong"])
            )
        questions = self.call("GET", "/collections")
        self.assertEqual(len(questions), 1)
        for eid in ids:
            self.assertIn(
                "共同概念练习",
                [
                    item["name"]
                    for item in self.call("GET", f"/features/review?exam_id={eid}")[
                        "items"
                    ]
                ],
            )

    def test_request_ids_correlate_create_and_failure_without_private_input(self):
        app = self.client.app
        with TestClient(
            AuditMiddleware(app, session_factory=sessionmaker(bind=self.engine)),
            raise_server_exceptions=False,
        ) as client:
            response = client.post(
                "/api/exams",
                headers=self.headers,
                json=dict(subject="private-subject", exam_date=str(date.today())),
            )
            rid = response.headers["x-request-id"]
            failed = client.get("/api/materials/999", headers=self.headers)
        self.assertEqual(len(rid), 32)
        self.assertEqual(len(failed.headers["x-request-id"]), 32)
        with Session(self.engine) as db:
            row = db.query(OperationLog).filter_by(request_id=rid).one()
            self.assertEqual(row.target_id, str(response.json()["id"]))
            self.assertNotIn("private-subject", row.path)

    def test_encrypted_backup_restores_database_files_and_secret_into_new_directory(
        self,
    ):
        from app.services.backups import snapshot, restore
        from sqlalchemy import create_engine

        item = self.upload()
        key = self.root / "backup.key"
        archive = snapshot(
            self.engine,
            self.root / "uploads",
            self.root / "backups",
            key,
            "synthetic-session-secret",
        )
        self.assertNotIn("概念".encode(), archive.read_bytes())
        destination = self.root / "restored"
        restore(archive, key, destination)
        engine = create_engine("sqlite:///" + str(destination / "fmzh.db"))
        try:
            with Session(engine) as db:
                row = db.get(Material, item["id"])
                self.assertEqual(row.title, item["title"])
                self.assertTrue(__import__("pathlib").Path(row.file_path).is_file())
                self.assertEqual(db.get(User, 1).username, "owner")
            self.assertEqual(
                (destination / ".runtime/session.key").read_text(),
                "synthetic-session-secret",
            )
            with self.assertRaises(ValueError):
                restore(archive, key, destination)
        finally:
            engine.dispose()

    def test_tampered_backup_never_creates_recovery_directory(self):
        from app.services.backups import snapshot, restore

        archive = snapshot(
            self.engine,
            self.root / "uploads",
            self.root / "backups",
            self.root / "backup.key",
            "session-secret",
        )
        content = bytearray(archive.read_bytes())
        content[-20] ^= 1
        archive.write_bytes(content)
        with self.assertRaises(Exception):
            restore(archive, self.root / "backup.key", self.root / "must-not-exist")
        self.assertFalse((self.root / "must-not-exist").exists())

    def test_daily_backup_does_not_mistake_another_database_for_its_own_snapshot(self):
        from app.services.backups import runner
        from sqlalchemy import create_engine
        from app.database import Base
        from types import SimpleNamespace

        second = create_engine("sqlite:///" + str(self.root / "second.db"))
        Base.metadata.create_all(second)
        settings = SimpleNamespace(
            BACKUP_ENABLED=True,
            BACKUP_INTERVAL_HOURS=24,
            BACKUP_DIR=str(self.root / "backups"),
            BACKUP_KEY_FILE=str(self.root / "key"),
            SECRET_KEY="synthetic-secret",
        )
        try:
            first = runner(self.engine, self.root / "uploads", settings)
            another = runner(second, self.root / "uploads", settings)
            self.assertTrue(first()["ok"])
            self.assertTrue(another()["ok"])
            self.assertEqual(len(list((self.root / "backups").glob("*.enc"))), 2)
            first()
            another()
            self.assertEqual(len(list((self.root / "backups").glob("*.enc"))), 2)
        finally:
            second.dispose()

    def test_fifty_simultaneous_database_requests_can_release_their_connections(self):
        from app.database import make_engine

        engine = make_engine(self.engine.url)
        barrier = Barrier(50)

        def read(_):
            with Session(engine) as db:
                name = db.get(User, 1).username
                barrier.wait(timeout=5)
                return name

        try:
            with ThreadPoolExecutor(max_workers=50) as pool:
                names = list(pool.map(read, range(50)))
            self.assertEqual(names, ["owner"] * 50)
        finally:
            engine.dispose()

    def test_generated_plan_with_only_completed_content_preserves_other_pending_work(
        self,
    ):
        from app.services.plan_service import create_tasks_from_plan
        from app.schemas.schemas import PlanItem

        eid = self.course()
        with Session(self.engine) as db:
            db.add_all(
                [
                    Task(
                        user_id=1,
                        exam_id=eid,
                        title="已做内容",
                        is_done=True,
                        plan_date=date.today(),
                        estimated_minutes=60,
                        source="ai",
                    ),
                    Task(
                        user_id=1,
                        exam_id=eid,
                        title="原计划待做",
                        plan_date=date.today(),
                        estimated_minutes=30,
                        source="ai",
                    ),
                ]
            )
            db.commit()
            result = create_tasks_from_plan(
                db,
                1,
                eid,
                None,
                [
                    PlanItem(
                        day=1,
                        date=str(date.today()),
                        title="已做内容",
                        estimated_minutes=60,
                    )
                ],
            )
            self.assertFalse(result["applied"])
            self.assertEqual(
                {row.title for row in db.query(Task)}, {"已做内容", "原计划待做"}
            )

    def test_completed_minutes_are_credited_once_across_repeated_plan_titles(self):
        from app.services.plan_service import create_tasks_from_plan
        from app.schemas.schemas import PlanItem

        eid = self.course()
        with Session(self.engine) as db:
            db.add(
                Task(
                    user_id=1,
                    exam_id=eid,
                    title="同一知识点",
                    is_done=True,
                    plan_date=date.today(),
                    estimated_minutes=60,
                    source="ai",
                )
            )
            db.commit()
            result = create_tasks_from_plan(
                db,
                1,
                eid,
                None,
                [
                    PlanItem(
                        day=1,
                        date=str(date.today()),
                        title="同一知识点",
                        estimated_minutes=50,
                    )
                    for _ in range(3)
                ],
            )
            self.assertTrue(result["applied"])
            self.assertEqual(
                sum(
                    row.estimated_minutes
                    for row in db.query(Task).filter(Task.is_done.is_(False))
                ),
                90,
            )
