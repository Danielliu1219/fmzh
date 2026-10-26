import json
import unittest
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base, get_db
from app.models.models import OperationLog, User
from app.routers import admin, auth, exams, ai, materials
from app.services.audit import AuditMiddleware
from app.utils.security import create_access_token, get_current_user, hash_password


class AuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = hash_password('StudyQA123')

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.engine = create_engine('sqlite:///' + (self.root / 'test.db').as_posix(), connect_args={'check_same_thread': False})
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.owner = User(username='owner', hashed_password=self.password)
        self.admin = User(username='admin', hashed_password=self.password, is_admin=True)
        self.db.add_all([self.owner, self.admin]); self.db.commit()
        self.owner_headers = {'Authorization': 'Bearer ' + create_access_token(self.owner)}
        self.admin_headers = {'Authorization': 'Bearer ' + create_access_token(self.admin)}
        app = FastAPI()
        def database():
            with Session(self.engine) as db: yield db
        app.dependency_overrides[get_db] = database
        @app.post('/api/tasks')
        def synthetic_failure(request: Request, user=Depends(get_current_user)):
            if request.headers.get('X-Fail'): raise RuntimeError('injected')
            return {'ok': True}
        for route, prefix in [(auth, 'auth'), (admin, 'admin'), (exams, 'exams'), (ai, 'ai'), (materials, 'materials')]:
            app.include_router(route.router, prefix='/api/' + prefix)
        app.add_middleware(AuditMiddleware, session_factory=lambda: Session(self.engine))
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        self.client.close(); self.db.close(); self.engine.dispose(); self.temp.cleanup()

    def logs(self, params=None):
        response = self.client.get('/api/admin/operation-logs', params=params, headers=self.admin_headers)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_login_success_and_failure_with_minimal_actor_snapshot(self):
        response = self.client.post('/api/auth/login', json={'username': 'owner', 'password': 'wrong-secret'})
        self.assertEqual(response.status_code, 401)
        failed = self.logs()['items'][0]
        self.assertEqual((failed['actor_name'], failed['actor_id'], failed['outcome']), ('owner', None, 'failure'))
        response = self.client.post('/api/auth/login', json={'username': 'owner', 'password': 'StudyQA123'})
        self.assertEqual(response.status_code, 200, response.text)
        success = self.logs()['items'][0]
        self.assertEqual(success['actor_id'], self.owner.id)
        self.assertEqual(success['status_code'], 200)
        serialized = json.dumps(self.logs())
        for secret in ('StudyQA123', 'wrong-secret', response.json()['access_token'], self.password):
            self.assertNotIn(secret, serialized)

    def test_no_body_query_or_bearer_credentials_stored(self):
        self.client.post('/api/tasks?password=never-store-this', headers=self.owner_headers,
                         json={'text': 'private materials body', 'password': 'secret-value'})
        record = self.logs()['items'][0]
        self.assertEqual(record['path'], '/api/tasks')
        data = json.dumps(self.logs())
        for secret in ('never-store-this', 'private materials body', 'secret-value', self.owner_headers['Authorization']):
            self.assertNotIn(secret, data)

    def test_empty_local_route_path_for_real_upload_is_audited(self):
        with patch.object(materials, 'UPLOAD_DIR', self.root):
            response = self.client.post('/api/materials', headers=self.owner_headers,
                                        data={'title': 'test'}, files={'file': ('test.txt', b'private-source-text', 'text/plain')})
        self.assertEqual(response.status_code, 200, response.text)
        record = self.logs()['items'][0]
        self.assertEqual(record['action'], 'material.upload')
        self.assertNotIn('private-source-text', json.dumps(self.logs()))

    def test_failed_500_is_logged_without_masking_server_status(self):
        response = self.client.post('/api/tasks', headers={**self.owner_headers, 'X-Fail': 'yes'})
        self.assertEqual(response.status_code, 500)
        record = self.logs()['items'][0]
        self.assertEqual((record['status_code'], record['outcome']), (500, 'failure'))

    def test_invalid_bearer_cannot_forge_actor(self):
        response = self.client.post('/api/tasks', headers={'Authorization': 'Bearer forged'})
        self.assertEqual(response.status_code, 401)
        self.assertIsNone(self.logs()['items'][0]['actor_id'])

    def test_student_and_anonymous_cannot_read_or_modify_logs(self):
        self.assertEqual(self.client.get('/api/admin/operation-logs', headers=self.owner_headers).status_code, 403)
        self.assertEqual(self.client.get('/api/admin/operation-logs').status_code, 401)
        self.assertEqual(self.client.delete('/api/admin/operation-logs/1', headers=self.admin_headers).status_code, 404)

    def test_mutation_denied_for_student_still_logs_authenticated_actor(self):
        response = self.client.delete('/api/admin/courses/123', headers=self.owner_headers)
        self.assertEqual(response.status_code, 403)
        record = self.logs()['items'][0]
        self.assertEqual((record['actor_id'], record['action'], record['target_id']), (self.owner.id, 'admin.course.delete', '123'))

    def test_page_filters_and_reads_do_not_recursively_create_logs(self):
        self.client.post('/api/tasks', headers=self.owner_headers)
        self.client.post('/api/tasks', headers={**self.owner_headers, 'X-Fail': 'yes'})
        self.assertEqual(self.logs({'page_size': 1})['total'], 2)
        self.assertEqual(len(self.logs({'page': 2, 'page_size': 1})['items']), 1)
        self.assertEqual(self.logs({'outcome': 'failure', 'action': 'task.create', 'actor': 'owner'})['total'], 1)
        self.assertEqual(self.logs()['total'], 2)
        for params in [{'page': 0}, {'page_size': 101}, {'action': 'invalid'}, {'outcome': 'unknown'}]:
            self.assertEqual(self.client.get('/api/admin/operation-logs', params=params, headers=self.admin_headers).status_code, 422)

    def test_beijing_date_filter_includes_boundaries_once(self):
        for stamp in [datetime(2026, 10, 25, 15, 59, 59), datetime(2026, 10, 25, 16), datetime(2026, 10, 26, 15, 59, 59), datetime(2026, 10, 26, 16)]:
            self.db.add(OperationLog(actor_name='boundary', action='auth.login', method='POST', path='/api/auth/login', status_code=200, created_at=stamp))
        self.db.commit()
        result = self.logs({'date_from': '2026-10-26', 'date_to': '2026-10-26', 'actor': 'boundary'})
        self.assertEqual(result['total'], 2)
        self.assertTrue(all(row['created_at'].endswith(('Z', '+00:00')) for row in result['items']))

    def test_account_deletion_preserves_audit_snapshot(self):
        self.client.post('/api/tasks', headers=self.owner_headers)
        with patch.object(auth, 'UPLOAD_DIR', self.root):
            response = self.client.delete('/api/auth/me', headers=self.owner_headers)
        self.assertEqual(response.status_code, 200, response.text)
        result = self.logs()['items']
        self.assertEqual(len(result), 2)
        self.assertTrue(all(row['actor_name'] == 'owner' for row in result))
        self.assertEqual(result[0]['action'], 'auth.delete')

    def test_audit_storage_failure_does_not_reverse_business_response(self):
        with patch.object(AuditMiddleware, 'record', side_effect=None) as record:
            self.assertEqual(self.client.post('/api/tasks', headers=self.owner_headers).status_code, 200)
            record.assert_called_once()
        def unavailable(): raise RuntimeError('injected audit storage failure')
        with self.assertLogs('app.services.audit', level='ERROR'):
            AuditMiddleware(None, session_factory=unavailable).record({})


if __name__ == '__main__': unittest.main()
