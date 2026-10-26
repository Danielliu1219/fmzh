import json
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi import Depends, FastAPI, Header
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.database import Base, get_db
from app.models.models import (
    Analysis, Collection, Exam, FileCleanupJob, FocusSession, Material,
    Notification, QaConversation, QaMessage, QuizAttempt, Reminder, Task, User, UserProfile,
)
from app.routers import admin, dashboard, exams, focus, materials
from app.services import deletion
from app.services.schema_upgrade import upgrade_schema
from app.utils.security import get_current_user


class DeletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.engine = create_engine('sqlite:///' + (self.root / 'test.db').as_posix(), connect_args={'check_same_thread': False})
        @event.listens_for(self.engine, 'connect')
        def enable_fk(connection, _):
            connection.execute('PRAGMA foreign_keys=ON')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, autoflush=False)
        self.owner = User(username='owner', hashed_password='unused')
        self.peer = User(username='peer', hashed_password='unused')
        self.admin = User(username='admin', hashed_password='unused', is_admin=True)
        self.db.add_all([self.owner, self.peer, self.admin]); self.db.commit()
        app = FastAPI()
        def database():
            with Session(self.engine, autoflush=False) as db:
                yield db
        def current(x_user_id: int = Header(default=self.owner.id), db=Depends(get_db)):
            return db.get(User, x_user_id)
        app.dependency_overrides[get_db] = database
        app.dependency_overrides[get_current_user] = current
        for route, prefix in [(exams, 'exams'), (materials, 'materials'), (admin, 'admin'), (dashboard, ''), (focus, 'focus')]:
            app.include_router(route.router, prefix='/api' + ('/' + prefix if prefix else ''))
        self.client = TestClient(app, raise_server_exceptions=False)
        self.upload_patch = patch.object(deletion, 'UPLOAD_DIR', self.root)
        self.upload_patch.start()

    def tearDown(self):
        self.client.close(); self.upload_patch.stop(); self.db.close(); self.engine.dispose(); self.temp.cleanup()

    def material(self, owner=None, path=None):
        path = path or self.root / 'shared.txt'
        path.write_text('test', encoding='utf-8')
        row = Material(user_id=(owner or self.owner).id, title='资料', file_path=str(path), file_type='txt')
        self.db.add(row); self.db.flush()
        self.db.add(Collection(user_id=self.peer.id, item_type='material', material_id=row.id))
        self.db.commit()
        return row

    def exam_graph(self):
        exam = Exam(user_id=self.owner.id, subject='数学', exam_date=date.today() + timedelta(days=4))
        self.db.add(exam); self.db.flush()
        profile = UserProfile(user_id=self.owner.id, exam_id=exam.id)
        self.db.add(profile); self.db.flush()
        analysis = Analysis(user_id=self.owner.id, exam_id=exam.id, profile_id=profile.id, result_json='{}')
        self.db.add(analysis); self.db.flush()
        task = Task(user_id=self.owner.id, exam_id=exam.id, analysis_id=analysis.id, title='复习', plan_date=date.today())
        conversation = QaConversation(user_id=self.owner.id, exam_id=exam.id)
        material = self.material()
        material.exam_id = exam.id
        self.db.add_all([task, conversation]); self.db.flush()
        self.db.add(QaMessage(conversation_id=conversation.id, role='user', content='问题'))
        self.db.add(QuizAttempt(user_id=self.owner.id, exam_id=exam.id, analysis_id=analysis.id, subject='数学', questions_json='[]'))
        self.db.add(FocusSession(user_id=self.owner.id, exam_id=exam.id, duration_minutes=25, start_time=datetime.now(), end_time=datetime.now()))
        for kind, target, created in [('exam', exam.id, exam.created_at), ('task', task.id, task.created_at)]:
            self.db.add(Reminder(user_id=self.owner.id, target_type=kind, target_id=target, target_created_at=created))
            self.db.add(Notification(user_id=self.owner.id, occurrence_key=kind, target_type=kind, target_id=target, target_created_at=created, title='提醒', content='内容', due_at=datetime.now(), created_at=datetime.now()))
        self.db.commit()
        return exam, material

    def test_exam_deletion_cleans_graph_and_preserves_material_and_history(self):
        exam, material = self.exam_graph()
        response = self.client.delete(f'/api/exams/{exam.id}')
        self.assertEqual(response.status_code, 200, response.text)
        self.db.expire_all()
        for model in (Exam, Task, UserProfile, Analysis, QuizAttempt, QaConversation, QaMessage, Reminder, Notification):
            self.assertEqual(self.db.query(model).count(), 0, model.__name__)
        self.assertIsNone(self.db.get(Material, material.id).exam_id)
        self.assertTrue(Path(material.file_path).exists())
        session = self.db.query(FocusSession).one()
        self.assertIsNone(session.exam_id)
        self.assertEqual(session.subject_snapshot, '数学')
        stats = self.client.get('/api/stats/overview').json()
        self.assertEqual(stats['total_minutes'], 25)
        self.assertEqual(stats['subjects'][0]['minutes'], 25)
        self.assertTrue(stats['subjects'][0]['archived'])
        weekly = self.client.post('/api/reports/weekly', json={}).json()
        self.assertEqual(weekly['total_minutes'], 25)
        self.assertIsNone(weekly['subjects'][0]['mastery'])
        self.assertTrue(self.client.get('/api/focus/today').json()['by_exam'][0]['archived'])
        self.assertEqual(self.client.get('/api/focus/sessions').json()[0]['subject'], '数学')

    def test_other_user_cannot_delete_exam(self):
        exam, _ = self.exam_graph()
        response = self.client.delete(f'/api/exams/{exam.id}', headers={'X-User-ID': str(self.peer.id)})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.db.query(Task).count(), 1)

    def test_exam_commit_failure_rolls_back_every_change(self):
        exam, material = self.exam_graph()
        with patch.object(Session, 'commit', side_effect=RuntimeError('injected')):
            self.assertEqual(self.client.delete(f'/api/exams/{exam.id}').status_code, 500)
        self.db.expire_all()
        self.assertIsNotNone(self.db.get(Exam, exam.id))
        self.assertEqual(self.db.query(Task).count(), 1)
        self.assertEqual(self.db.get(Material, material.id).exam_id, exam.id)
        self.assertEqual(self.db.query(FocusSession).one().exam_id, exam.id)

    def test_admin_delete_cleans_file_and_all_collection_references(self):
        material = self.material()
        response = self.client.delete(f'/api/admin/materials/{material.id}', headers={'X-User-ID': str(self.admin.id)})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(Path(material.file_path).exists())
        self.assertEqual(self.db.query(Collection).count(), 0)
        self.assertEqual(self.db.query(FileCleanupJob).count(), 0)

    def test_student_delete_uses_same_cleanup(self):
        material = self.material()
        self.assertEqual(self.client.delete(f'/api/materials/{material.id}').status_code, 200)
        self.assertFalse(Path(material.file_path).exists())
        self.assertEqual(self.db.query(Collection).count(), 0)

    def test_shared_file_survives_until_last_reference_deleted(self):
        first = self.material()
        second = self.material(owner=self.peer, path=Path(first.file_path))
        self.assertEqual(self.client.delete(f'/api/materials/{first.id}').status_code, 200)
        self.assertTrue(Path(second.file_path).exists())
        self.assertEqual(self.client.delete(f'/api/materials/{second.id}', headers={'X-User-ID': str(self.peer.id)}).status_code, 200)
        self.assertFalse(Path(second.file_path).exists())

    def test_material_commit_failure_never_removes_file(self):
        material = self.material()
        with patch.object(Session, 'commit', side_effect=RuntimeError('injected')):
            self.assertEqual(self.client.delete(f'/api/materials/{material.id}').status_code, 500)
        self.assertTrue(Path(material.file_path).exists())
        self.assertEqual(self.db.query(Collection).count(), 1)
        self.assertEqual(self.db.query(FileCleanupJob).count(), 0)

    def test_unlink_failure_is_durable_and_admin_can_retry(self):
        material = self.material()
        path = Path(material.file_path)
        with patch.object(Path, 'unlink', side_effect=PermissionError('injected')):
            response = self.client.delete(f'/api/materials/{material.id}')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()['cleanup_pending'])
        self.assertTrue(Path(material.file_path).exists())
        self.db.expire_all()
        self.assertEqual(self.db.query(FileCleanupJob).one().attempts, 1)
        self.assertEqual(self.client.post('/api/admin/file-cleanups/retry').status_code, 403)
        response = self.client.post('/api/admin/file-cleanups/retry', headers={'X-User-ID': str(self.admin.id)})
        self.assertEqual(response.json()['pending'], 0)
        self.assertFalse(path.exists())

    def test_retry_rechecks_new_shared_reference(self):
        material = self.material()
        path = Path(material.file_path)
        with patch.object(Path, 'unlink', side_effect=PermissionError('injected')):
            self.client.delete(f'/api/materials/{material.id}')
        self.db.expunge(material)
        self.material(owner=self.peer, path=path)
        result = deletion.retry_file_cleanup(self.db)
        self.assertEqual(result['pending'], 0)
        self.assertTrue(path.exists())

    def test_cross_user_and_non_admin_material_delete_rejected(self):
        material = self.material(owner=self.peer)
        self.assertEqual(self.client.delete(f'/api/materials/{material.id}').status_code, 404)
        self.assertEqual(self.client.delete(f'/api/admin/materials/{material.id}').status_code, 403)
        self.assertTrue(Path(material.file_path).exists())

    def test_post_commit_cleanup_database_failure_keeps_success_and_durable_job(self):
        material = self.material()
        with patch.object(deletion, 'retry_file_cleanup', side_effect=OperationalError('injected', {}, RuntimeError('locked'))):
            with self.assertLogs('app.services.deletion', level='ERROR'):
                response = self.client.delete(f'/api/materials/{material.id}')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()['cleanup_pending'])
        self.assertEqual(self.db.query(Material).count(), 0)
        self.assertEqual(self.db.query(FileCleanupJob).count(), 1)
        self.assertTrue(Path(material.file_path).exists())

    def test_outside_upload_root_is_rejected(self):
        material = self.material()
        with patch.object(deletion, 'UPLOAD_DIR', self.root / 'other'):
            self.assertEqual(self.client.delete(f'/api/materials/{material.id}').status_code, 409)
        self.assertTrue(Path(material.file_path).exists())

    def test_snapshot_upgrade_is_additive_and_repeatable(self):
        self.exam_graph()
        self.db.close()
        with self.engine.begin() as conn:
            conn.execute(text('ALTER TABLE focus_sessions DROP COLUMN subject_snapshot'))
        upgrade_schema(self.engine)
        upgrade_schema(self.engine)
        with self.engine.connect() as conn:
            self.assertIn('subject_snapshot', [row[1] for row in conn.execute(text('PRAGMA table_info(focus_sessions)'))])
            snapshot, minutes = conn.execute(text('SELECT subject_snapshot, duration_minutes FROM focus_sessions')).one()
            self.assertEqual((snapshot, minutes), ('数学', 25))


if __name__ == '__main__':
    unittest.main()
