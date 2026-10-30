"""9.3 真实会话撤销与专注保存顺序；前端取消由独立测试覆盖。"""
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from sqlalchemy.orm import Session
from app.models.models import User
from app.routers import focus
import test_auth_quizzes as fixtures

class LogoutConfirmationTests(unittest.TestCase):
    setUp=fixtures.AuthQuizTests.setUp
    tearDown=fixtures.AuthQuizTests.tearDown
    register=fixtures.AuthQuizTests.register
    call=fixtures.AuthQuizTests.call
    def test_focus_before_revoke_is_durable_old_session_cannot_write(self):
        self.client.app.include_router(focus.router,prefix='/api/focus')
        self.call('POST','/focus/sessions',dict(duration_minutes=1));self.call('POST','/auth/logout')
        self.call('POST','/focus/sessions',dict(duration_minutes=1),status=401)
        fresh=self.call('POST','/auth/login',dict(username='owner',password='StudyQA123'))
        rows=self.call('GET','/focus/sessions',headers={'Authorization':'Bearer '+fresh['access_token']})
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['duration_minutes'],1)
    def test_failed_commit_leaves_session_valid(self):
        with Session(self.engine) as db:original=db.get(User,self.owner['user']['id']).auth_key
        with patch('sqlalchemy.orm.Session.commit',side_effect=RuntimeError('storage unavailable')):
            response=self.client.post('/api/auth/logout',headers=self.headers)
            self.assertEqual(response.status_code,500)
        self.call('GET','/auth/me')
        with Session(self.engine) as db:self.assertEqual(db.get(User,self.owner['user']['id']).auth_key,original)
    def test_revoke_only_affects_confirmed_account(self):
        peer=self.register('peer');fresh=self.call('POST','/auth/login',dict(username='owner',password='StudyQA123'))
        self.call('POST','/auth/logout');self.call('GET','/auth/me',headers={'Authorization':'Bearer '+fresh['access_token']},status=401)
        self.call('GET','/auth/me',headers={'Authorization':'Bearer '+peer['access_token']})
    def test_concurrent_logout_commits_one_revocation(self):
        barrier=Barrier(2)
        def logout(_):
            barrier.wait();return self.client.post('/api/auth/logout',headers=self.headers).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(logout,range(2)))
        self.assertEqual(sorted(codes),[200,401]);self.call('GET','/auth/me',status=401)
