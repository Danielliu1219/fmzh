"""重现真实旧库缺列导致注册500；增量迁移保留旧字段/记录/密码与会话。"""
import unittest
from datetime import date, timedelta

from sqlalchemy import inspect, text

from app.models.models import Exam, User
from app.services.schema_upgrade import upgrade_schema
from app.utils.security import hash_password, verify_password
import test_auth_quizzes as fixtures


class RegistrationUpgradeTests(unittest.TestCase):
    setUp=fixtures.AuthQuizTests.setUp
    tearDown=fixtures.AuthQuizTests.tearDown
    register=fixtures.AuthQuizTests.register
    call=fixtures.AuthQuizTests.call

    def legacy(self):
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO exams (id,user_id,subject,exam_date) VALUES (1,1,'原有考试',:day)"),{'day':str(date.today()+timedelta(days=7))})
            for name in ('class_name','avatar','is_admin','is_banned','failed_attempts','locked_until'):
                conn.execute(text(f'ALTER TABLE users DROP COLUMN {name}'))
            conn.execute(text('ALTER TABLE exams DROP COLUMN color'))

    def snapshot(self):
        with self.engine.connect() as conn:
            return [tuple(row) for row in conn.execute(text('SELECT id,username,hashed_password,auth_key,nickname,student_no,major,grade,created_at FROM users ORDER BY id'))]

    def test_legacy_registration_was_500_and_upgrade_restores_registration_login(self):
        self.legacy()
        before=self.snapshot()
        response=self.client.post('/api/auth/register',json={'username':'new_user','password':'StudyQA123'})
        self.assertEqual(response.status_code,500)
        upgrade_schema(self.engine)
        upgrade_schema(self.engine)
        self.assertEqual(before,self.snapshot())
        fresh=self.register('new_user')
        login=self.client.post('/api/auth/login',json={'username':'new_user','password':'StudyQA123'})
        self.assertEqual(login.status_code,200,login.text)
        self.assertEqual(login.json()['user']['id'],fresh['user']['id'])
        self.assertEqual(self.call('GET','/auth/me')['username'],'owner')
        with self.engine.connect() as conn:
            self.assertEqual(tuple(conn.execute(text('SELECT subject,color FROM exams WHERE id=1')).one()),('原有考试',''))

    def test_upgrade_defaults_are_safe_and_do_not_overwrite_existing_fields(self):
        self.legacy();upgrade_schema(self.engine)
        with self.engine.begin() as conn:
            self.assertEqual(tuple(conn.execute(text('SELECT class_name,avatar,is_admin,is_banned,failed_attempts,locked_until FROM users WHERE id=1')).one()),('','',0,0,0,None))
            conn.execute(text("UPDATE users SET class_name='已有班级',avatar='#123456',is_admin=1,is_banned=1,failed_attempts=2 WHERE id=1"))
            conn.execute(text("UPDATE exams SET color='#abcdef' WHERE id=1"))
        upgrade_schema(self.engine)
        with self.engine.connect() as conn:
            self.assertEqual(tuple(conn.execute(text('SELECT class_name,avatar,is_admin,is_banned,failed_attempts FROM users WHERE id=1')).one()),('已有班级','#123456',1,1,2))
            self.assertEqual(conn.execute(text('SELECT color FROM exams WHERE id=1')).scalar(),'#abcdef')

    def test_all_model_columns_are_available_after_legacy_upgrade(self):
        self.legacy();upgrade_schema(self.engine)
        schema=inspect(self.engine)
        for model in (User,Exam):
            self.assertFalse(set(model.__table__.columns.keys())-{c['name'] for c in schema.get_columns(model.__tablename__)})

    def test_unicode_password_within_character_limit_registers_and_logs_in(self):
        for index,password in enumerate(('测'*32,'🙂'*24,'汉'*24+'ab')):
            with self.subTest(case=index):
                payload={'username':f'unicode_{index}','password':password}
                response=self.client.post('/api/auth/register',json=payload)
                self.assertEqual(response.status_code,200,response.text)
                login=self.client.post('/api/auth/login',json=payload)
                self.assertEqual(login.status_code,200,login.text)

    def test_password_suffix_is_not_truncated_and_legacy_hashes_remain_valid(self):
        password='汉'*25+'first'
        encoded=hash_password(password)
        self.assertTrue(verify_password(password,encoded))
        self.assertFalse(verify_password('汉'*25+'other',encoded))
        self.assertTrue(verify_password('StudyQA123',hash_password('StudyQA123')))
        self.assertFalse(verify_password('wrong',encoded))

    def test_long_unicode_password_also_works_when_changed_and_reset(self):
        self.call('POST','/auth/change-password',{'old_password':'StudyQA123','new_password':'新'*32})
        response=self.client.post('/api/auth/login',json={'username':'owner','password':'新'*32})
        self.assertEqual(response.status_code,200,response.text)
        reset=self.client.post('/api/auth/reset-password/verify',json={'username':'owner','student_no':'20240001'})
        self.assertEqual(reset.status_code,200,reset.text)
        confirm=self.client.post('/api/auth/reset-password/confirm',json={'reset_token':reset.json()['reset_token'],'new_password':'重'*32})
        self.assertEqual(confirm.status_code,200,confirm.text)
        self.assertEqual(self.client.post('/api/auth/login',json={'username':'owner','password':'重'*32}).status_code,200)
