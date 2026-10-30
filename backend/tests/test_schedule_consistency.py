"""真实SQLite事务与接口：全科重排/交叉写入、模型等待与原子落库。"""
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from threading import Barrier, Event
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.models import Analysis, Exam, FocusGoal, Material, StudySetting, Task, User, UserProfile
from app.routers import ai, study
from app.services import study_planner
from app.services.task_conflicts import lock_schedule
import test_task_details as fixtures


class ScheduleConsistencyTests(unittest.TestCase):
    tearDown = fixtures.TaskDetailsTests.tearDown
    call = fixtures.TaskDetailsTests.call

    def setUp(self):
        fixtures.TaskDetailsTests.setUp(self)
        with Session(self.engine) as db:
            db.get(Exam, 1).exam_date = date.today()+timedelta(days=6)
            db.add_all([
                Task(id=1, user_id=1, exam_id=1, title='AI复习', plan_date=date.today()+timedelta(days=3), estimated_minutes=150, source='ai'),
                Task(id=2, user_id=1, exam_id=1, title='已完成记录', plan_date=date.today(), estimated_minutes=20, source='ai', is_done=True),
                Task(id=3, user_id=1, exam_id=1, title='手动安排', plan_date=date.today(), estimated_minutes=30, source='manual'),
                UserProfile(user_id=1, exam_id=1, raw_text='还有6天，每天2小时，数学基础一般，希望考80分', target='medium', learning_status='medium', available_days=6, daily_hours=2, is_complete=True),
                Material(user_id=1, exam_id=1, title='重点', source_type='老师重点', file_path='isolated-fixture.txt', file_type='txt', text_content='极限与积分是重点，需要练习和复盘错题。', parse_status='done'),
            ])
            db.commit()

    def state(self):
        with Session(self.engine) as db:
            return [(t.id, t.title, str(t.plan_date), t.estimated_minutes, t.is_done, t.source) for t in db.query(Task).order_by(Task.id)]

    def preview(self):
        return self.call('GET', '/study/plan/preview')

    def confirm(self, plan, status=200):
        return self.call('POST', '/study/plan/confirm', {'fingerprint':plan['fingerprint']}, status=status)

    def analyze(self, status=200):
        return self.call('POST', '/ai/analyze', {'exam_id':1}, status=status)

    def edit_in_other_transaction(self, change):
        with Session(self.engine) as db:
            lock_schedule(db, 1)
            change(db)
            db.commit()

    def test_readonly_preview_and_atomic_confirmation_preserve_work(self):
        before = self.state()
        plan = self.preview()
        self.assertEqual(before, self.state())
        self.confirm(plan)
        after = self.state()
        self.assertEqual(sum(t[3] for t in after), 200)
        self.assertEqual(before[1:], [t for t in after if t[0] in (2, 3)])
        self.assertTrue(all(day['minutes'] <= 120 for day in self.preview()['days']))
        self.assertEqual(sorted((t[2],t[3]) for t in after if t[5]=='ai' and not t[4]),
                         sorted((a['date'],a['minutes']) for a in plan['assignments']))

    def test_each_schedule_input_invalidates_old_preview_without_writing(self):
        changes = [
            ('PUT','/tasks/1',{'title':'新标题'}),
            ('POST','/tasks',{'exam_id':1,'title':'新增任务','plan_date':str(date.today()),'estimated_minutes':10}),
            ('POST','/tasks/1/checkin',None),
            ('DELETE','/tasks/1/checkin',None),
            ('DELETE','/tasks/3',None),
            ('PUT','/study/settings',{'daily_minutes':180}),
            ('PUT','/exams/1',{'exam_date':str(date.today()+timedelta(days=7))}),
            ('POST','/exams',{'subject':'新增考试','exam_date':str(date.today()+timedelta(days=8))}),
        ]
        for method, path, body in changes:
            with self.subTest(path=path, method=method):
                old = self.preview()
                self.call(method,path,body)
                current = self.state()
                self.confirm(old,409)
                self.assertEqual(current,self.state())

    def test_confirm_refreshes_objects_loaded_before_another_commit(self):
        plan = self.preview()
        with Session(self.engine,autoflush=False) as db:
            user = db.get(User,1)
            cached_task = db.get(Task,1)
            cached_budget = db.get(StudySetting,1)
            self.edit_in_other_transaction(lambda other:setattr(other.get(StudySetting,1),'daily_minutes',180))
            self.assertEqual(cached_budget.daily_minutes,120)
            with self.assertRaises(HTTPException) as error:
                study.plan_confirm(study.ConfirmIn(fingerprint=plan['fingerprint']),user,db)
            self.assertEqual(error.exception.status_code,409)
            self.assertEqual(db.get(StudySetting,1).daily_minutes,180)
            self.assertEqual(cached_task.title,'AI复习')

    def test_commit_failure_rolls_back_all_split_rows(self):
        plan = self.preview()
        before = self.state()
        with patch('sqlalchemy.orm.Session.commit',side_effect=RuntimeError('injected commit failure')):
            self.confirm(plan,500)
        self.assertEqual(before,self.state())
        self.confirm(plan)

    def confirm_while_writer_waits(self, method, path, body=None):
        plan = self.preview()
        applying, release, writer_started = Event(), Event(), Event()
        original = study_planner.apply
        def slow_apply(*args, **kwargs):
            applying.set()
            if not release.wait(3):
                raise RuntimeError('test did not release confirmation')
            return original(*args,**kwargs)
        def write():
            writer_started.set()
            return self.client.request(method,'/api'+path,json=body)
        with patch.object(study_planner,'apply',side_effect=slow_apply), ThreadPoolExecutor(max_workers=2) as pool:
            confirming = pool.submit(self.client.post,'/api/study/plan/confirm',json={'fingerprint':plan['fingerprint']})
            try:
                self.assertTrue(applying.wait(3))
                writer = pool.submit(write)
                self.assertTrue(writer_started.wait(3))
                self.assertFalse(writer.done())
                self.assertFalse(Event().wait(.15) or writer.done(), 'writer must wait until confirmation commits')
            finally:
                release.set()
            response = confirming.result(timeout=5)
            self.assertEqual(response.status_code,200,response.text)
            response = writer.result(timeout=5)
            self.assertEqual(response.status_code,200,response.text)

    def test_manual_task_write_waits_for_confirm_and_is_not_lost(self):
        self.confirm_while_writer_waits('POST','/tasks',{'exam_id':1,'title':'并发新增','plan_date':str(date.today()+timedelta(days=4)),'estimated_minutes':30})
        self.assertTrue(any(t[1]=='并发新增' for t in self.state()))
        self.assertEqual(sum(t[3] for t in self.state()),230)

    def test_checkin_waits_for_confirm_and_completion_survives(self):
        self.confirm_while_writer_waits('POST','/tasks/1/checkin')
        self.assertTrue(next(t for t in self.state() if t[0]==1)[4])
        self.assertEqual(sum(t[3] for t in self.state()),200)

    def test_budget_change_waits_then_saves_budget_and_goal_together(self):
        self.confirm_while_writer_waits('PUT','/study/settings',{'daily_minutes':180})
        with Session(self.engine) as db:
            self.assertEqual(db.get(StudySetting,1).daily_minutes,180)
            self.assertEqual(db.query(FocusGoal).filter_by(user_id=1,goal_date=date.today()).one().target_minutes,180)

    def test_exam_deletion_waits_and_leaves_no_orphan_tasks(self):
        self.confirm_while_writer_waits('DELETE','/exams/1')
        with Session(self.engine) as db:
            self.assertIsNone(db.get(Exam,1))
            self.assertEqual(db.query(Task).filter_by(exam_id=1).count(),0)

    def test_two_confirmations_reject_the_second_old_preview(self):
        old = self.preview()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _:self.client.post('/api/study/plan/confirm',json={'fingerprint':old['fingerprint']}), range(2)))
        self.assertEqual(sorted(r.status_code for r in results),[200,409])
        self.assertEqual(sum(t[3] for t in self.state()),200)

    def test_deleted_or_revoked_account_cannot_acquire_schedule_lock(self):
        with Session(self.engine) as db:
            for uid, key in ((999,None),(1,'stale-auth-key')):
                with self.subTest(uid=uid):
                    with self.assertRaises(HTTPException) as error:
                        lock_schedule(db,uid,auth_key=key)
                    self.assertEqual(error.exception.status_code,401)
                    db.rollback()

    def test_analyze_releases_lock_during_model_and_rejects_changed_inputs(self):
        original = ai.prompts.mock_generate_analysis
        changes = [
            lambda db:setattr(db.get(StudySetting,1),'daily_minutes',180),
            lambda db:setattr(db.get(Task,1),'is_done',True),
            lambda db:setattr(db.get(Exam,1),'exam_date',date.today()+timedelta(days=8)),
            lambda db:setattr(db.query(UserProfile).filter_by(user_id=1).first(),'raw_text','更新画像'),
            lambda db:setattr(db.query(Material).filter_by(user_id=1).first(),'weight',.7),
        ]
        for index, change in enumerate(changes):
            with self.subTest(change=index):
                def generate(*args,**kwargs):
                    self.edit_in_other_transaction(change)
                    return original(*args,**kwargs)
                with patch.object(ai.prompts,'mock_generate_analysis',side_effect=generate):
                    self.analyze(409)
                with Session(self.engine) as db:
                    self.assertEqual(db.query(Analysis).count(),0)

    def test_model_success_and_failed_task_write_rollback_analysis_together(self):
        before = self.state()
        with patch.object(study_planner,'apply',side_effect=RuntimeError('injected task write failure')):
            self.analyze(500)
        self.assertEqual(before,self.state())
        with Session(self.engine) as db:
            self.assertEqual(db.query(Analysis).count(),0)
        self.analyze()
        with Session(self.engine) as db:
            self.assertEqual(db.query(Analysis).count(),1)
            self.assertTrue(db.query(Task).filter(Task.analysis_id.is_not(None)).count())

    def test_concurrent_analyses_save_one_result_and_one_task_plan(self):
        barrier = Barrier(2)
        original = ai.prompts.mock_generate_analysis
        def generate(*args,**kwargs):
            barrier.wait(timeout=4)
            return original(*args,**kwargs)
        with patch.object(ai.prompts,'mock_generate_analysis',side_effect=generate), ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _:self.client.post('/api/ai/analyze',json={'exam_id':1}),range(2)))
        self.assertEqual(sorted(r.status_code for r in results),[200,409],[r.text for r in results])
        with Session(self.engine) as db:
            self.assertEqual(db.query(Analysis).count(),1)
            self.assertEqual(db.query(Task).filter_by(id=2).one().title,'已完成记录')

    def test_profile_wait_does_not_overwrite_newer_profile(self):
        original = ai.prompts.mock_extract_profile
        def extract(*args,**kwargs):
            self.edit_in_other_transaction(lambda db:setattr(db.query(UserProfile).filter_by(user_id=1).first(),'raw_text','另一处已保存'))
            return original(*args,**kwargs)
        with patch.object(ai.prompts,'mock_extract_profile',side_effect=extract):
            self.call('POST','/ai/profile',{'exam_id':1,'raw_text':'每天2小时，数学基础一般，希望考80分，还有6天'},status=409)
        with Session(self.engine) as db:
            self.assertEqual(db.query(UserProfile).filter_by(user_id=1).one().raw_text,'另一处已保存')

    def test_concurrent_first_profiles_do_not_create_duplicate_records(self):
        with Session(self.engine) as db:
            db.query(UserProfile).delete()
            db.commit()
        barrier = Barrier(2)
        original = ai.prompts.mock_extract_profile
        def extract(*args,**kwargs):
            barrier.wait(timeout=4)
            return original(*args,**kwargs)
        with patch.object(ai.prompts,'mock_extract_profile',side_effect=extract), ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _:self.client.post('/api/ai/profile',json={'exam_id':1,'raw_text':'每天2小时，还有6天，数学基础一般，目标80分'}),range(2)))
        self.assertEqual(sorted(r.status_code for r in results),[200,409],[r.text for r in results])
        with Session(self.engine) as db:
            self.assertEqual(db.query(UserProfile).filter_by(user_id=1,exam_id=1).count(),1)

    def test_budget_commit_failure_preserves_both_budget_and_goal(self):
        with patch('sqlalchemy.orm.Session.commit',side_effect=RuntimeError('injected commit failure')):
            self.call('PUT','/study/settings',{'daily_minutes':180},status=500)
        with Session(self.engine) as db:
            self.assertEqual(db.get(StudySetting,1).daily_minutes,120)
            self.assertEqual(db.query(FocusGoal).filter_by(user_id=1).count(),0)

    def test_foreign_account_cannot_confirm_or_change_owner_plan(self):
        old = self.preview()
        before = self.state()
        self.call('POST','/study/plan/confirm',{'fingerprint':old['fingerprint']},status=409,headers={'X-User':'2'})
        self.call('POST','/tasks/1/checkin',status=404,headers={'X-User':'2'})
        self.call('PUT','/exams/1',{'subject':'越权修改'},status=404,headers={'X-User':'2'})
        self.assertEqual(before,self.state())

    def test_logout_during_model_cannot_save_under_new_session_identity(self):
        original = ai.prompts.mock_generate_analysis
        def generate(*args,**kwargs):
            self.edit_in_other_transaction(lambda db:setattr(db.get(User,1),'auth_key','rotated-session'))
            return original(*args,**kwargs)
        with patch.object(ai.prompts,'mock_generate_analysis',side_effect=generate):
            self.analyze(401)
        with Session(self.engine) as db:
            self.assertEqual(db.query(Analysis).count(),0)
