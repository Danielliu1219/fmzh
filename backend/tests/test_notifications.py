"""模块 6 的隔离 HTTP 回归；内存数据库，不导入 main，不接触原库和上传目录。"""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime, timedelta
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.models import Exam, Notification, NotificationPreference, Reminder, Task
from app.routers import auth, exams, notifications, tasks
from app.services import notifications as service

NOW = datetime(2026, 10, 17, 3)  # 北京时间 11:00


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, autoflush=False)
        app = FastAPI()
        def database():
            yield self.db
        app.dependency_overrides[get_db] = database
        for name, router in [('auth', auth), ('exams', exams), ('tasks', tasks), ('notifications', notifications)]:
            app.include_router(router.router, prefix='/api/' + name)
        self.client = TestClient(app)
        self.clock = patch.object(service, 'utcnow', return_value=NOW)
        self.clock.start()
        self.headers = self.account('owner')
        self.exam = self.call('POST', '/exams', {'subject': '高数', 'exam_date': '2026-10-17'})
        self.task = self.call('POST', '/tasks', {'exam_id': self.exam['id'], 'title': '极限练习', 'plan_date': '2026-10-17'})

    def tearDown(self):
        self.clock.stop(); self.client.close(); self.db.close(); self.engine.dispose()

    def account(self, name):
        data = self.client.post('/api/auth/register', json={'username': name, 'password': 'StudyQA123', 'student_no': '20240001'}).json()
        return {'Authorization': 'Bearer ' + data['access_token']}

    def call(self, method, path, payload=None, status=200, headers=None):
        r = self.client.request(method, '/api' + path, json=payload, headers=self.headers if headers is None else headers)
        self.assertEqual(r.status_code, status, r.text)
        return r.json()

    def rule(self, kind='task', clock='11:00', advance=0, enabled=True):
        id = self.task['id'] if kind == 'task' else self.exam['id']
        return self.call('PUT', f'/notifications/reminders/{kind}/{id}', {'enabled': enabled, 'event_time': clock, 'advance_minutes': advance})

    def check(self):
        return self.call('POST', '/notifications/check')['created']

    def history(self, query=''):
        return self.call('GET', '/notifications' + query)

    def test_timezone_boundary_and_no_early_or_get_trigger(self):
        self.assertFalse(self.call('GET', f"/notifications/reminders/task/{self.task['id']}")['enabled'])
        self.assertEqual(self.rule(clock='12:00', advance=59)['due_at'], '2026-10-17T03:01:00+00:00')
        self.assertEqual(self.check(), 0)
        self.rule(clock='12:00', advance=60)
        self.assertEqual(self.history()['total'], 0)  # GET 不生成
        self.assertEqual(self.check(), 1)  # 边界相等时到期
        self.assertEqual(self.history()['items'][0]['created_at'], '2026-10-17T03:00:00+00:00')

    def test_repeated_check_and_delete_do_not_regenerate(self):
        self.rule(); self.assertEqual(self.check(), 1); self.assertEqual(self.check(), 0)
        id = self.history()['items'][0]['id']
        self.call('DELETE', f'/notifications/{id}')
        self.assertEqual(self.check(), 0)
        self.assertEqual(self.history()['total'], 0)
        self.assertEqual(self.db.query(Notification).count(), 1)

    def test_read_unread_read_all_and_pagination(self):
        self.rule(); self.rule('exam'); self.assertEqual(self.check(), 2)
        id = self.history()['items'][0]['id']
        self.call('PATCH', f'/notifications/{id}', {'is_read': True})
        self.assertEqual(self.history('?unread_only=true')['total'], 1)
        self.call('PATCH', f'/notifications/{id}', {'is_read': False})
        self.assertEqual(self.history()['unread_count'], 2)
        self.assertEqual(len(self.history('?page_size=1')['items']), 1)
        self.call('POST', '/notifications/read-all')
        self.assertEqual(self.history()['unread_count'], 0)
        self.assertEqual(self.history()['total'], 2)

    def test_master_and_category_switches_persist(self):
        self.rule(); self.rule('exam')
        self.call('PUT', '/notifications/preferences', {'enabled': False})
        self.assertEqual(self.check(), 0)
        self.assertFalse(self.call('GET', '/notifications/preferences')['enabled'])
        self.call('PUT', '/notifications/preferences', {'enabled': True, 'exam_enabled': False, 'task_enabled': True})
        self.assertEqual(self.check(), 1)
        self.call('PUT', '/notifications/preferences', {'enabled': True})
        self.assertEqual(self.check(), 1)
        self.rule(enabled=False)
        self.assertFalse(self.call('GET', f"/notifications/reminders/task/{self.task['id']}")['enabled'])

    def test_completed_deleted_or_expired_sources_are_skipped(self):
        self.rule(); self.rule('exam')
        self.call('POST', f"/tasks/{self.task['id']}/checkin")
        self.call('PUT', f"/exams/{self.exam['id']}", {'exam_date': '2026-10-16'})
        self.assertEqual(self.check(), 0)
        self.call('DELETE', f"/exams/{self.exam['id']}")
        self.assertEqual(self.check(), 0)

    def test_reschedule_follows_new_date_preserving_history(self):
        self.rule(); self.check()
        self.call('PUT', f"/tasks/{self.task['id']}", {'plan_date': '2026-10-18'})
        data = self.call('GET', f"/notifications/reminders/task/{self.task['id']}")
        self.assertTrue(data['due_at'].startswith('2026-10-18'))
        self.assertEqual(self.check(), 0)
        self.assertEqual(service.check_due(self.db, 1, NOW + timedelta(days=1)), 1)
        self.assertEqual(self.history()['total'], 2)

    def test_user_isolation_and_authentication(self):
        self.rule(); self.check(); id = self.history()['items'][0]['id']
        peer = self.account('peer')
        self.assertEqual(self.call('GET', '/notifications', headers=peer)['total'], 0)
        for method, path, payload in [('PATCH', f'/notifications/{id}', {'is_read': True}), ('DELETE', f'/notifications/{id}', None),
                ('GET', f"/notifications/reminders/task/{self.task['id']}", None),
                ('PUT', f"/notifications/reminders/exam/{self.exam['id']}", {'enabled': True, 'event_time': '09:00', 'advance_minutes': 0})]:
            self.call(method, path, payload, status=404, headers=peer)
        self.call('POST', '/notifications/check', status=401, headers={})

    def test_validation_and_missing_source(self):
        for clock, advance in [('25:00', 0), ('9:00', 0), ('11:00', -1), ('11:00', 43201)]:
            self.call('PUT', f"/notifications/reminders/task/{self.task['id']}", {'enabled': True, 'event_time': clock, 'advance_minutes': advance}, status=422)
        self.call('GET', '/notifications/reminders/task/999', status=404)
        self.call('GET', '/notifications?page=0', status=422)

    def test_account_deactivation_cleans_notification_data(self):
        self.rule(); self.check()
        self.call('PUT', '/notifications/preferences', {'enabled': True})
        with TemporaryDirectory() as directory, patch.object(auth, 'UPLOAD_DIR', Path(directory)):
            self.call('DELETE', '/auth/me')
        for model in (Notification, Reminder, NotificationPreference):
            self.assertEqual(self.db.query(model).count(), 0)

    def test_deleted_source_id_reuse_does_not_inherit_reminder_or_link(self):
        self.rule(); self.check()
        old = self.db.get(Task, self.task['id']); created = old.created_at
        self.db.delete(old); self.db.commit()
        self.db.add(Task(id=self.task['id'], user_id=1, exam_id=self.exam['id'], title='新的事项', plan_date=old.plan_date,
                         created_at=created + timedelta(seconds=1)))
        self.db.commit()
        self.assertFalse(self.call('GET', f"/notifications/reminders/task/{self.task['id']}")['enabled'])
        self.assertEqual(self.check(), 0)
        self.assertFalse(self.history()['items'][0]['target_available'])


if __name__ == '__main__':
    unittest.main()
