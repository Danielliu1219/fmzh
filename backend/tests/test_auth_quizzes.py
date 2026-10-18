"""账号隔离与自测闭环 HTTP 回归；只使用临时数据库和上传目录。"""
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import jwt
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, get_db
from app.models.models import Analysis, Collection, Exam, Material, MoodRecord, QuizAttempt, User, UserProfile
from app.routers import ai, auth, collections, exams, quizzes
from app.services.schema_upgrade import upgrade_schema
from app.services.mistakes import save_question


QUESTIONS = [
    dict(question="单选题", options=["A. 一", "B. 二"], answer="B", analysis="选第二项", knowledge_point="概念"),
    dict(kind="multiple", question="多选题", options=["A. 一", "B. 二", "C. 三"], answer="A,C"),
    dict(kind="boolean", question="判断题", answer="true"),
    dict(kind="fill", question="填空题", answer="42", accepted_answers=["四十二"]),
]


class AuthQuizTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.engine = create_engine('sqlite:///' + (self.root / 'test.db').as_posix(), connect_args={'check_same_thread': False})
        Base.metadata.create_all(self.engine)
        app = FastAPI()
        def database():
            with Session(self.engine, autoflush=False) as db:
                yield db
        app.dependency_overrides[get_db] = database
        for name, route in [('auth', auth), ('exams', exams), ('ai', ai), ('collections', collections), ('quizzes', quizzes)]:
            app.include_router(route.router, prefix='/api/' + name)
        self.client = TestClient(app, raise_server_exceptions=False)
        self.upload_patch = patch.object(auth, 'UPLOAD_DIR', self.root / 'uploads')
        self.upload_patch.start()
        self.owner = self.register('owner')
        self.headers = {'Authorization': 'Bearer ' + self.owner['access_token']}

    def tearDown(self):
        self.upload_patch.stop()
        self.client.close()
        self.engine.dispose()
        self.temp.cleanup()

    def register(self, name):
        r = self.client.post('/api/auth/register', json=dict(username=name, password='StudyQA123', student_no='20240001'))
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def call(self, method, path, data=None, status=200, headers=None):
        r = self.client.request(method, '/api' + path, json=data, headers=self.headers if headers is None else headers)
        self.assertEqual(r.status_code, status, r.text)
        return r.json()

    def analysis(self, questions=None):
        with Session(self.engine) as db:
            exam = Exam(user_id=self.owner['user']['id'], subject='测试科目', exam_date=date.today()+timedelta(days=10))
            db.add(exam); db.flush()
            profile = UserProfile(user_id=exam.user_id, exam_id=exam.id)
            db.add(profile); db.flush()
            analysis = Analysis(user_id=exam.user_id, exam_id=exam.id, profile_id=profile.id, result_json=json.dumps({'quiz': questions or QUESTIONS}, ensure_ascii=False))
            db.add(analysis); db.commit()
            return analysis.id, exam.id

    def start(self, analysis_id=None):
        if analysis_id is None: analysis_id, _ = self.analysis()
        return self.call('POST', '/quizzes', {'analysis_id': analysis_id}, status=201)

    def reset_token(self):
        return self.call('POST', '/auth/reset-password/verify', dict(username='owner', student_no='20240001'))['reset_token']

    def test_reset_and_legacy_tokens_cannot_authenticate(self):
        reset = self.reset_token()
        self.call('GET', '/auth/me', status=401, headers={'Authorization': 'Bearer '+reset})
        legacy = jwt.encode({'sub': str(self.owner['user']['id']), 'exp': datetime.now(timezone.utc)+timedelta(minutes=5)}, settings.SECRET_KEY, algorithm='HS256')
        self.call('GET', '/auth/me', status=401, headers={'Authorization': 'Bearer '+legacy})
        self.call('POST', '/auth/reset-password/confirm', {'reset_token': self.owner['access_token'], 'new_password': 'Changed123'}, status=400)

    def test_reset_is_single_use_and_revokes_all_old_credentials(self):
        reset = self.reset_token()
        other_reset = self.reset_token()
        self.call('POST', '/auth/reset-password/confirm', {'reset_token': reset, 'new_password': 'Changed123'})
        self.call('GET', '/auth/me', status=401)
        for token in [reset, other_reset]:
            self.call('POST', '/auth/reset-password/confirm', {'reset_token': token, 'new_password': 'Another123'}, status=400)
        self.call('POST', '/auth/login', dict(username='owner', password='StudyQA123'), status=401)
        self.call('POST', '/auth/login', dict(username='owner', password='Changed123'))

    def test_password_change_and_logout_revoke_sessions(self):
        reset = self.reset_token()
        self.call('POST', '/auth/change-password', {'old_password': 'StudyQA123', 'new_password': 'Changed123'})
        self.call('GET', '/auth/me', status=401)
        self.call('POST', '/auth/reset-password/confirm', {'reset_token': reset, 'new_password': 'Another123'}, status=400)
        fresh = self.call('POST', '/auth/login', dict(username='owner', password='Changed123'))
        self.headers = {'Authorization': 'Bearer '+fresh['access_token']}
        self.call('POST', '/auth/logout')
        self.call('GET', '/auth/me', status=401)

    def test_locked_and_banned_accounts_are_denied(self):
        with Session(self.engine) as db:
            user=db.get(User,self.owner['user']['id']); user.is_banned=True; db.commit()
        self.call('GET', '/auth/me', status=403)
        with Session(self.engine) as db:
            user=db.get(User,self.owner['user']['id']); user.is_banned=False; user.locked_until=datetime.now()+timedelta(minutes=30); db.commit()
        self.call('GET', '/auth/me', status=403)
        reset=self.reset_token()
        self.call('POST','/auth/reset-password/confirm',{'reset_token':reset,'new_password':'Changed123'})
        self.call('POST','/auth/login',dict(username='owner',password='Changed123'))

    def test_deactivate_cleans_all_owner_data_and_prevents_id_reuse(self):
        analysis_id, exam_id = self.analysis()
        attempt = self.start(analysis_id)
        self.call('POST', f"/quizzes/{attempt['id']}/submit", {'answers':['A',[], '', '']})
        reset = self.reset_token()
        upload = self.root/'uploads'/str(self.owner['user']['id'])/'file.txt'
        upload.parent.mkdir(parents=True); upload.write_text('owned')
        with Session(self.engine) as db:
            db.add(MoodRecord(user_id=self.owner['user']['id'], record_date=date.today(), mood_score=1))
            db.add(Material(user_id=self.owner['user']['id'], exam_id=exam_id, title='资料', file_path=str(upload), file_type='txt'))
            db.commit()
        self.call('DELETE', '/auth/me')
        self.assertFalse(upload.exists())
        with Session(self.engine) as db:
            for table in Base.metadata.sorted_tables:
                if 'user_id' in table.c:
                    self.assertEqual(db.execute(table.select().where(table.c.user_id == self.owner['user']['id'])).all(), [], table.name)
        recreated = self.register('owner')
        self.assertEqual(recreated['user']['id'], self.owner['user']['id'])
        self.call('GET','/auth/me',status=401)
        self.call('POST','/auth/reset-password/confirm',{'reset_token':reset,'new_password':'Changed123'},status=400)
        fresh={'Authorization':'Bearer '+recreated['access_token']}
        self.assertEqual(self.call('GET','/collections',headers=fresh),[])

    def test_cross_user_quiz_and_collection_access_denied(self):
        analysis_id,_=self.analysis()
        attempt=self.start(analysis_id)
        other=self.register('another')
        headers={'Authorization':'Bearer '+other['access_token']}
        self.call('POST','/quizzes',{'analysis_id':analysis_id},status=404,headers=headers)
        self.call('GET',f'/quizzes?analysis_id={analysis_id}',status=404,headers=headers)
        self.call('GET',f"/quizzes/{attempt['id']}",status=404,headers=headers)
        self.call('POST',f"/quizzes/{attempt['id']}/submit",{'answers':['B',['A','C'],'true','42']},status=404,headers=headers)
        own=self.call('POST','/collections',{'item_type':'question','title':'私有错题'},status=201)
        self.assertEqual(self.call('GET','/collections',headers=headers),[])
        self.call('DELETE',f"/collections/{own['id']}",status=404,headers=headers)

    def test_expired_credentials_are_rejected(self):
        payload=jwt.decode(self.owner['access_token'],settings.SECRET_KEY,algorithms=['HS256'])
        payload['exp']=datetime.now(timezone.utc)-timedelta(seconds=1)
        expired=jwt.encode(payload,settings.SECRET_KEY,algorithm='HS256')
        self.call('GET','/auth/me',status=401,headers={'Authorization':'Bearer '+expired})

    def test_registration_skips_legacy_orphan_ids(self):
        with Session(self.engine) as db:
            db.add(Collection(user_id=99,item_type='question',title='历史残留'))
            db.commit()
        fresh=self.register('fresh')
        self.assertGreater(fresh['user']['id'],99)
        self.assertEqual(self.call('GET','/collections',headers={'Authorization':'Bearer '+fresh['access_token']}),[])

    def test_deactivate_refuses_file_paths_outside_upload_root(self):
        outside=self.root/'keep.txt';outside.write_text('unrelated')
        with Session(self.engine) as db:
            db.add(Material(user_id=self.owner['user']['id'],title='异常路径',file_path=str(outside),file_type='txt'));db.commit()
        self.call('DELETE','/auth/me',status=409)
        self.assertEqual(outside.read_text(),'unrelated')
        self.call('GET','/auth/me')

    def test_deactivate_preserves_another_users_shared_file_and_data(self):
        other=self.register('another')
        shared=self.root/'uploads'/'demo'/'shared.txt'
        shared.parent.mkdir(parents=True);shared.write_text('shared')
        with Session(self.engine) as db:
            for user_id in [self.owner['user']['id'],other['user']['id']]:
                db.add(Material(user_id=user_id,title='共享演示资料',file_path=str(shared),file_type='txt'))
            db.add(Collection(user_id=other['user']['id'],item_type='question',title='另一个账号的题'))
            db.commit()
        self.call('DELETE','/auth/me')
        self.assertTrue(shared.exists())
        headers={'Authorization':'Bearer '+other['access_token']}
        self.call('GET','/auth/me',headers=headers)
        self.assertEqual(len(self.call('GET','/collections',headers=headers)),1)

    def test_concurrent_reset_consumes_credential_once(self):
        reset=self.reset_token()
        def submit(_):
            return self.client.post('/api/auth/reset-password/confirm',json={'reset_token':reset,'new_password':'Changed123'})
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses=list(pool.map(submit,range(2)))
        self.assertEqual(sorted(r.status_code for r in responses),[200,400],[r.text for r in responses])

    def test_answers_hidden_until_submit_and_four_types_grade(self):
        analysis_id,exam_id=self.analysis()
        public=self.call('GET',f'/ai/analyses/{exam_id}')['result']['quiz']
        self.assertTrue(all(q['answer']=='' and q['analysis']=='' and q['accepted_answers']==[] for q in public))
        attempt=self.start(analysis_id)
        self.assertIsNone(attempt['result'])
        self.assertTrue(all('answer' not in q and 'analysis' not in q for q in attempt['questions']))
        graded=self.call('POST',f"/quizzes/{attempt['id']}/submit",{'answers':['b',['C','A'],'正确','４２']})
        self.assertEqual(graded['result']['score'],100)
        self.assertEqual(graded['result']['correct'],4)
        self.assertEqual(self.call('GET','/collections'),[])
        self.assertEqual(self.call('GET',f"/quizzes/{attempt['id']}")['result'],graded['result'])

    def test_wrong_blank_and_repeat_submission_do_not_duplicate_mistakes(self):
        analysis_id,_=self.analysis()
        attempt=self.start(analysis_id)
        answers=['A',['A'],'false','']
        first=self.call('POST',f"/quizzes/{attempt['id']}/submit",{'answers':answers})
        self.assertEqual(first['result']['score'],0)
        self.assertEqual(first['result']['unanswered'],1)
        self.assertEqual(first['result']['mistakes_added'],4)
        repeat=self.call('POST',f"/quizzes/{attempt['id']}/submit",{'answers':answers})
        self.assertEqual(first['result'],repeat['result'])
        self.call('POST',f"/quizzes/{attempt['id']}/submit",{'answers':['B',['A','C'],'true','42']},status=409)
        again=self.start(analysis_id)
        self.assertEqual(self.call('POST',f"/quizzes/{again['id']}/submit",{'answers':answers})['result']['mistakes_added'],0)
        book=self.call('GET','/collections?source=quiz')
        self.assertEqual(len(book),4)
        self.assertIn('submitted_answer',json.loads(book[0]['content']))

    def test_snapshot_and_explicit_fill_alternative(self):
        analysis_id,_=self.analysis()
        attempt=self.start(analysis_id)
        with Session(self.engine) as db:
            db.get(Analysis,analysis_id).result_json=json.dumps({'quiz':[]});db.commit()
        result=self.call('POST',f"/quizzes/{attempt['id']}/submit",{'answers':['B',['A','C'],'true','四十二']})
        self.assertEqual(result['result']['score'],100)

    def test_invalid_submission_keeps_attempt_open(self):
        attempt=self.start()
        for answers in [['B'],['Z',[], '', ''],['B',['Z'],'','']]:
            self.call('POST',f"/quizzes/{attempt['id']}/submit",{'answers':answers},status=422)
        self.assertEqual(self.call('GET',f"/quizzes/{attempt['id']}")['status'],'active')
        self.assertEqual(self.call('GET','/collections'),[])

    def test_mistake_write_failure_rolls_back_entire_submission(self):
        attempt=self.start()
        calls=[]
        def fail_second(*args,**kwargs):
            calls.append(1)
            if len(calls)>1:raise RuntimeError('simulated storage failure')
            return save_question(*args,**kwargs)
        with patch.object(quizzes,'save_question',side_effect=fail_second):
            r=self.client.post(f"/api/quizzes/{attempt['id']}/submit",json={'answers':['A',[],'','']},headers=self.headers)
        self.assertEqual(r.status_code,500)
        self.assertEqual(self.call('GET',f"/quizzes/{attempt['id']}")['status'],'active')
        self.assertEqual(self.call('GET','/collections'),[])

    def test_batch_and_concurrent_wrong_question_deduplication(self):
        data={'mistakes':[{'title':'同一题','content':'解析'},{'title':' 同一题 ','content':'解析'}]}
        self.assertEqual(len(self.call('POST','/collections/mistakes',data,status=201)),1)
        analysis_id,_=self.analysis()
        attempts=[self.start(analysis_id) for _ in range(2)]
        def submit(a):
            return self.client.post(f"/api/quizzes/{a['id']}/submit",json={'answers':['A',[],'','']},headers=self.headers)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(submit,attempts))
        self.assertEqual([r.status_code for r in results],[200,200],[r.text for r in results])
        self.assertEqual(len(self.call('GET','/collections')),5)

    def test_legacy_schema_upgrade_preserves_data_and_is_idempotent(self):
        engine=create_engine('sqlite://')
        with engine.begin() as conn:
            conn.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT)'))
            conn.execute(text("INSERT INTO users VALUES (1,'existing'),(2,'another')"))
            conn.execute(text('CREATE TABLE collections (id INTEGER PRIMARY KEY,user_id INTEGER,item_type TEXT,title TEXT)'))
            conn.execute(text("INSERT INTO collections VALUES (1,1,'question','重复题'),(2,1,'question','重复题')"))
        upgrade_schema(engine);upgrade_schema(engine)
        with engine.connect() as conn:
            keys=conn.execute(text('SELECT auth_key FROM users')).scalars().all()
            self.assertTrue(all(keys));self.assertEqual(len(set(keys)),2)
            self.assertEqual(conn.execute(text('SELECT COUNT(*) FROM collections')).scalar(),2)
            self.assertEqual(conn.execute(text('SELECT COUNT(question_key) FROM collections')).scalar(),1)
        engine.dispose()


if __name__=='__main__':unittest.main()
