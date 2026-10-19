import json
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.database import Base, get_db
from app.models.models import Analysis, Exam, Material, QaConversation, QaMessage, QuizAttempt, StudySetting, Task, User, UserProfile
from app.routers import ai, auth, materials
from app.services import study_planner
from app.services.schema_upgrade import upgrade_schema
from app.utils.security import get_current_user


class ReplanningTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.engine = create_engine('sqlite:///' + (self.root/'qa.db').as_posix(), connect_args={'check_same_thread': False})
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, autoflush=False)
        self.user = User(username='owner', hashed_password='unused')
        self.db.add(self.user); self.db.flush()
        self.exam = Exam(user_id=self.user.id, subject='数学', exam_date=date.today()+timedelta(days=3))
        self.other_exam = Exam(user_id=self.user.id, subject='英语', exam_date=date.today()+timedelta(days=4))
        self.db.add_all([self.exam, self.other_exam]); self.db.flush()
        self.db.add(StudySetting(user_id=self.user.id, daily_minutes=60))
        profile = UserProfile(user_id=self.user.id, exam_id=self.exam.id, target='pass', target_band='D', daily_hours=1, available_days=3, is_complete=True)
        self.db.add(profile); self.db.flush()
        self.analysis = Analysis(user_id=self.user.id, exam_id=self.exam.id, profile_id=profile.id, result_json=json.dumps({'course':'数学','knowledge_points':[{'name':'积分','weight':0.7}],'review_plan':[],'quiz':[{'question':'积分题','options':['A','B'],'answer':'B'}]}))
        self.manual = Task(user_id=self.user.id, exam_id=self.exam.id, title='手动任务', plan_date=date.today(), estimated_minutes=45, source='manual')
        self.ai_task = Task(user_id=self.user.id, exam_id=self.exam.id, title='积分', plan_date=date.today(), estimated_minutes=90, source='ai', priority=2)
        self.db.add_all([self.analysis,self.manual,self.ai_task]); self.db.commit()
        self.app = FastAPI()
        def database():
            with Session(self.engine, autoflush=False) as db: yield db
        self.app.dependency_overrides[get_db] = database
        def current_user(db: Session = Depends(get_db)):
            return db.get(User, self.user.id)
        self.app.dependency_overrides[get_current_user] = current_user
        for route,name in [(ai,'ai'),(auth,'auth'),(materials,'materials')]: self.app.include_router(route.router,prefix='/api/'+name)
        self.client = TestClient(self.app,raise_server_exceptions=False)
        self.path = f'/api/ai/analyses/{self.exam.id}/replan'

    def tearDown(self):
        self.client.close();self.db.close();self.engine.dispose();self.temp.cleanup()

    def state(self):
        self.db.expire_all()
        return (self.db.get(Analysis,self.analysis.id).result_json, [(t.id,t.title,t.plan_date,t.estimated_minutes,t.priority,t.is_done) for t in self.db.query(Task).order_by(Task.id)])

    def preview(self):
        response=self.client.post(self.path,json={'apply':False})
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def apply(self,preview,status=200):
        response=self.client.post(self.path,json={'apply':True,'fingerprint':preview['fingerprint']})
        self.assertEqual(response.status_code,status,response.text)
        return response

    def attempt(self, correct=False, exam=None):
        row=QuizAttempt(user_id=self.user.id,exam_id=(exam or self.exam).id,analysis_id=self.analysis.id,subject=(exam or self.exam).subject,questions_json='[]',status='submitted',submitted_at=datetime.now(),result_json=json.dumps({'items':[{'question':'积分题','knowledge_point':'积分','correct':correct}]}))
        self.db.add(row);self.db.commit()

    def test_preview_is_read_only_and_fixed_time_reserved(self):
        old=self.state();p=self.preview()
        self.assertEqual(old,self.state())
        self.assertTrue(all(d['minutes']<=60 for d in p['scheduling']['days']))
        self.assertEqual(sum(a['minutes'] for a in p['scheduling']['assignments']),90)
        self.assertEqual(sum(a['minutes'] for a in p['scheduling']['assignments'] if a['date']==str(date.today())),15)

    def test_confirm_matches_preview_and_preserves_total_and_manual(self):
        p=self.preview();self.apply(p);self.db.expire_all()
        self.assertEqual(sum(t.estimated_minutes for t in self.db.query(Task)),135)
        self.assertEqual(self.db.get(Task,self.manual.id).plan_date,date.today())
        actual=sorted((str(t.plan_date),t.estimated_minutes) for t in self.db.query(Task).filter(Task.source=='ai'))
        expected=sorted((a['date'],a['minutes']) for a in p['scheduling']['assignments'])
        self.assertEqual(actual,expected)

    def test_feedback_adds_practice_once_and_repeated_apply_does_not_ratchet(self):
        self.attempt();p=self.preview();self.assertEqual(p['wrong_questions'],1)
        self.assertTrue(any('专项练习' in a['title'] for a in p['plan']))
        self.apply(p);first_weight=self.preview()['weights'][0]['new_weight']
        again=self.preview();self.apply(again);self.db.expire_all()
        self.assertEqual(self.preview()['weights'][0]['new_weight'],first_weight)
        self.assertEqual(sum(t.estimated_minutes for t in self.db.query(Task).filter(Task.source=='ai')),120)

    def test_latest_correct_attempt_removes_old_wrong_feedback(self):
        self.attempt();self.apply(self.preview());self.attempt(correct=True)
        p=self.preview();self.assertEqual(p['wrong_questions'],0)
        self.assertLess(p['weights'][0]['new_weight'],0.8)

    def test_feedback_is_scoped_to_selected_subject(self):
        self.attempt(exam=self.other_exam)
        self.assertEqual(self.preview()['wrong_questions'],0)

    def test_budget_change_rejects_stale_confirm_without_writes(self):
        p=self.preview();self.db.get(StudySetting,self.user.id).daily_minutes=90;self.db.commit()
        old=self.state();self.apply(p,409);self.assertEqual(old,self.state())

    def test_new_quiz_rejects_stale_confirm(self):
        p=self.preview();self.attempt();old=self.state();self.apply(p,409);self.assertEqual(old,self.state())

    def test_task_change_rejects_stale_confirm(self):
        p=self.preview();self.manual.estimated_minutes=50;self.db.commit();old=self.state();self.apply(p,409);self.assertEqual(old,self.state())

    def test_conflicts_reject_all_writes(self):
        self.exam.exam_date=date.today()+timedelta(days=1);self.db.commit()
        old=self.state();p=self.preview();self.assertTrue(p['scheduling']['conflicts']);self.apply(p,409);self.assertEqual(old,self.state())

    def test_task_write_failure_rolls_back_tasks_and_analysis(self):
        self.attempt();p=self.preview();old=self.state();real_apply=study_planner.apply
        def fail(*a,**kw):
            real_apply(*a,**kw)
            a[0].flush()
            raise RuntimeError('simulated disk error')
        with patch.object(study_planner,'apply',side_effect=fail):self.apply(p,500)
        self.assertEqual(old,self.state())

    def test_expired_exam_is_rejected_without_writes(self):
        self.exam.exam_date=date.today()-timedelta(days=1);self.db.commit();old=self.state()
        self.assertEqual(self.client.post(self.path,json={'apply':False}).status_code,409)
        self.assertEqual(old,self.state())

    def test_completed_tasks_are_not_recreated(self):
        self.ai_task.is_done=True;self.ai_task.estimated_minutes=15;self.db.commit()
        p=self.preview();self.assertEqual(p['plan'],[]);self.apply(p)
        self.assertEqual(len(self.state()[1]),2)

    def test_cross_user_replan_denied(self):
        self.app.dependency_overrides[get_current_user]=lambda:User(id=999,auth_key='other')
        self.assertEqual(self.client.post(self.path,json={'apply':False}).status_code,404)

    def test_qa_history_cards_and_deactivation_cleanup(self):
        upload=self.root/'uploads';upload.mkdir();file=upload/'material.txt';file.write_text('积分用于求面积',encoding='utf-8')
        self.db.add(Material(user_id=self.user.id,exam_id=self.exam.id,title='老师重点',source_type='老师重点',weight=1.0,file_type='txt',file_path=str(file),text_content='积分用于求面积',parse_status='done'));self.db.commit()
        r=self.client.post('/api/ai/qa/conversations',json={'exam_id':self.exam.id});self.assertEqual(r.status_code,201,r.text);cid=r.json()['id']
        for content in ['积分是什么','积分如何求面积']:
            r=self.client.post(f'/api/ai/qa/conversations/{cid}/messages',json={'content':content});self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(len(r.json()['messages']),4)
        self.assertEqual(self.client.get(f'/api/ai/analyses/{self.exam.id}/mindmap').status_code,200)
        self.assertEqual(self.client.get(f'/api/ai/analyses/{self.exam.id}').json()['result']['quiz'][0]['answer'],'')
        with patch.object(auth,'UPLOAD_DIR',upload):
            r=self.client.delete('/api/auth/me');self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(self.db.query(QaConversation).count(),0);self.assertEqual(self.db.query(QaMessage).count(),0)

    def test_weight_migration_is_idempotent_and_preserves_adjusted_value(self):
        legacy=create_engine('sqlite:///' + (self.root/'legacy.db').as_posix())
        with legacy.begin() as c:
            c.execute(text('CREATE TABLE materials (id INTEGER PRIMARY KEY, source_type VARCHAR(32))'))
            c.execute(text("INSERT INTO materials VALUES (1,'老师重点'),(2,'历年题')"))
        # Existing upgrade tests already cover missing users/collections columns; complete remaining tables.
        Base.metadata.create_all(legacy);upgrade_schema(legacy)
        with legacy.begin() as c:
            self.assertEqual(c.execute(text('SELECT weight FROM materials WHERE id=1')).scalar(),1.0)
            c.execute(text('UPDATE materials SET weight=0.42 WHERE id=2'))
        upgrade_schema(legacy)
        with legacy.connect() as c:self.assertEqual(c.execute(text('SELECT weight FROM materials WHERE id=2')).scalar(),0.42)
        legacy.dispose()

if __name__=='__main__':unittest.main()
