"""7.1 原公式、北京时间、后台生命周期、幂等和只读/账号边界。"""
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from threading import Barrier, Event
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.models import DailyPressure, Exam, Task, User
from app.services import daily_pressure, pressure
import test_task_details as fixtures
import test_auth_quizzes as auth_fixtures

NOW = datetime(2026, 10, 30, 0, 0, tzinfo=timezone.utc)  # 北京时间08:00


class FormulaTests(unittest.TestCase):
    def test_existing_weights_and_empty_state_are_preserved(self):
        today = date(2026,10,30)
        exams = [SimpleNamespace(exam_date=today+timedelta(days=3))]
        tasks = [SimpleNamespace(plan_date=today-timedelta(days=1),is_done=False),SimpleNamespace(plan_date=today,is_done=True)]
        result = pressure.calculate(exams,tasks,today)
        self.assertEqual(result['score'],52.5)
        self.assertEqual(result['breakdown'],dict(exam_density=.25,task_backlog=.5,task_done_rate=.5,exam_proximity=1))
        self.assertEqual(pressure.calculate([],[],today)['score'],20)

    def test_seven_day_inclusion_and_twenty_one_day_proximity(self):
        today=NOW.date()
        rows=[SimpleNamespace(exam_date=today+timedelta(days=d)) for d in (-1,0,7,8)]
        self.assertEqual(pressure._exam_density(rows,today),.5)
        self.assertEqual(pressure._exam_proximity([SimpleNamespace(exam_date=today+timedelta(days=42))],today),.5)
        self.assertEqual(pressure._exam_proximity(rows[:1],today),0)

    def test_level_boundaries_are_unchanged(self):
        for score,level in [(0,'轻松'),(39.9,'轻松'),(40,'适中'),(59.9,'适中'),(60,'偏压'),(79.9,'偏压'),(80,'高压'),(100,'高压')]:
            self.assertEqual(pressure._level_of(score)[0],level)


class DailyPressureTests(unittest.TestCase):
    setUp=fixtures.TaskDetailsTests.setUp
    tearDown=fixtures.TaskDetailsTests.tearDown
    call=fixtures.TaskDetailsTests.call

    def factory(self):
        return Session(self.engine,autoflush=False)

    def seed(self):
        with self.factory() as db:
            db.get(Exam,1).exam_date=NOW.date()+timedelta(days=3)
            db.add_all([Task(user_id=1,exam_id=1,title='逾期',plan_date=NOW.date()-timedelta(days=1),estimated_minutes=60,is_done=False),Task(user_id=1,exam_id=1,title='完成',plan_date=NOW.date(),estimated_minutes=60,is_done=True)])
            db.commit()

    def count(self):
        with self.factory() as db:return db.query(DailyPressure).count()

    def test_get_is_readonly_and_missing_days_remain_explicit(self):
        with patch.object(pressure,'utcnow',return_value=NOW):
            data=self.call('GET','/features/pressure')
            self.assertEqual(data['date'],'2026-10-30');self.assertEqual(data['daily_status'],'pending');self.assertIsNone(data['daily_snapshot'])
            result=self.call('GET','/features/pressure/history')
            self.assertEqual(result['items'],[]);self.assertEqual(len(result['missing_dates']),7)
        self.assertEqual(self.count(),0)
        for days in ('0','32','bad'):self.call('GET','/features/pressure/history?days='+days,status=422)
        self.call('POST','/features/pressure/history',status=405)

    def test_capture_uses_original_formula_and_keeps_calculation_evidence(self):
        self.seed();self.assertTrue(daily_pressure.capture_user(self.factory,1,NOW,'startup'))
        with patch.object(pressure,'utcnow',return_value=NOW):
            value=self.call('GET','/features/pressure')
        stored=value['daily_snapshot']
        self.assertEqual((value['score'],stored['score']),(52.5,52.5))
        self.assertEqual((stored['record_date'],stored['source'],stored['formula_version']),('2026-10-30','startup','v1'))
        self.assertEqual(stored['computed_at'],'2026-10-30T00:00:00Z')
        self.assertEqual(stored['breakdown'],value['breakdown'])

    def test_daily_record_is_immutable_while_realtime_changes(self):
        self.seed();daily_pressure.capture_user(self.factory,1,NOW,'startup')
        with self.factory() as db:
            db.query(Task).filter(Task.user_id==1).update({Task.is_done:True});db.commit()
        self.assertFalse(daily_pressure.capture_user(self.factory,1,NOW+timedelta(hours=2),'scheduled'))
        with patch.object(pressure,'utcnow',return_value=NOW+timedelta(hours=2)):
            value=self.call('GET','/features/pressure')
        self.assertEqual(value['daily_snapshot']['score'],52.5);self.assertEqual(value['score'],27.5)
        self.assertEqual(value['daily_snapshot']['source'],'startup')

    def test_timezone_midnight_and_not_before_0005(self):
        before=datetime(2026,10,29,16,4,59,tzinfo=timezone.utc)
        self.assertEqual(daily_pressure.run_due(self.factory,before)['created'],0)
        self.assertEqual(daily_pressure.run_due(self.factory,before+timedelta(seconds=1))['created'],2)
        with self.factory() as db:self.assertEqual({r.record_date for r in db.query(DailyPressure)},{date(2026,10,30)})
        self.assertEqual(pressure.beijing_day(datetime(2026,10,29,15,59,tzinfo=timezone.utc)),date(2026,10,29))

    def test_repeated_poll_and_restart_do_not_rewrite_records(self):
        first=daily_pressure.run_due(self.factory,NOW,'startup')
        self.assertEqual(first['created'],2)
        second=daily_pressure.run_due(self.factory,NOW+timedelta(hours=3),'startup')
        self.assertEqual((second['created'],second['scanned']),(0,0));self.assertEqual(self.count(),2)

    def test_offline_gap_only_backfills_current_day(self):
        daily_pressure.run_due(self.factory,NOW,'startup')
        later=NOW+timedelta(days=7)
        daily_pressure.run_due(self.factory,later,'startup')
        with patch.object(pressure,'utcnow',return_value=later):result=self.call('GET','/features/pressure/history')
        self.assertEqual(len(result['items']),1);self.assertEqual(len(result['missing_dates']),6)
        self.assertEqual(result['items'][0]['record_date'],'2026-11-06')
        self.assertEqual(self.count(),4)

    def test_account_isolation_and_range(self):
        self.seed();daily_pressure.run_due(self.factory,NOW,'startup')
        with patch.object(pressure,'utcnow',return_value=NOW):
            owner=self.call('GET','/features/pressure/history?user_id=2&days=1')
            peer=self.call('GET','/features/pressure/history?days=1',headers={'x-user':'2'})
        self.assertEqual(len(owner['items']),1);self.assertEqual(owner['items'][0]['score'],52.5)
        self.assertNotEqual(owner['items'][0]['score'],peer['items'][0]['score'])
        self.assertEqual(owner['missing_dates'],[])

    def test_concurrent_workers_create_one_row(self):
        barrier=Barrier(2)
        def capture(_):
            barrier.wait();return daily_pressure.capture_user(self.factory,1,NOW,'scheduled')
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(capture,range(2)))
        self.assertEqual(sorted(results),[False,True]);self.assertEqual(self.count(),1)

    def test_one_failure_does_not_stop_others_and_next_poll_retries(self):
        original=daily_pressure.capture_user
        def capture(factory,user_id,now,source):
            if user_id==1:raise RuntimeError('injected account failure')
            return original(factory,user_id,now,source)
        with patch.object(daily_pressure,'capture_user',side_effect=capture),self.assertLogs(daily_pressure.logger,level='ERROR'):
            result=daily_pressure.run_due(self.factory,NOW)
        self.assertEqual((result['created'],result['failed']),(1,1))
        result=daily_pressure.run_due(self.factory,NOW)
        self.assertEqual((result['created'],result['failed']),(1,0));self.assertEqual(self.count(),2)

    def test_failed_commit_rolls_back_and_deleted_account_is_skipped(self):
        with patch('sqlalchemy.orm.Session.commit',side_effect=RuntimeError('injected database failure')):
            with self.assertRaises(RuntimeError):daily_pressure.capture_user(self.factory,1,NOW,'startup')
        self.assertEqual(self.count(),0)
        self.assertFalse(daily_pressure.capture_user(self.factory,999,NOW,'startup'))
        self.assertTrue(daily_pressure.capture_user(self.factory,1,NOW,'startup'))

    def test_existing_database_adds_only_missing_table_and_preserves_data(self):
        self.seed()
        with self.factory() as db:before=[(r.id,r.title,r.plan_date,r.is_done) for r in db.query(Task)]
        DailyPressure.__table__.drop(self.engine)
        Base.metadata.create_all(self.engine);Base.metadata.create_all(self.engine)
        self.assertEqual(len(inspect(self.engine).get_table_names()),22)
        with self.factory() as db:self.assertEqual(before,[(r.id,r.title,r.plan_date,r.is_done) for r in db.query(Task)])
        self.assertEqual(daily_pressure.run_due(self.factory,NOW,'startup')['created'],2)

    def test_background_without_http_requests_and_graceful_stop(self):
        current=[NOW]
        app=FastAPI(lifespan=daily_pressure.make_lifespan(self.factory,interval=.02,clock=lambda:current[0]))
        with TestClient(app):
            self.assertEqual(self.count(),2)
            current[0]=NOW+timedelta(days=1)
            for _ in range(100):
                if self.count()==4:break
                Event().wait(.01)
            self.assertEqual(self.count(),4)
            self.assertTrue(app.state.daily_pressure['running'])
            with self.factory() as db:self.assertEqual({r.source for r in db.query(DailyPressure)},{'startup','scheduled'})
        self.assertFalse(app.state.daily_pressure['running'])
        current[0]+=timedelta(days=1);Event().wait(.05);self.assertEqual(self.count(),4)


class DailyPressureDeletionTests(unittest.TestCase):
    setUp=auth_fixtures.AuthQuizTests.setUp
    tearDown=auth_fixtures.AuthQuizTests.tearDown
    register=auth_fixtures.AuthQuizTests.register
    call=auth_fixtures.AuthQuizTests.call
    def test_deactivate_removes_daily_history_and_leaves_peer(self):
        peer=self.register('peer')
        factory=sessionmaker(bind=self.engine,autoflush=False)
        daily_pressure.run_due(factory,NOW,'startup')
        self.call('DELETE','/auth/me')
        with factory() as db:
            rows=db.query(DailyPressure).all()
            self.assertEqual(len(rows),1);self.assertEqual(rows[0].user_id,peer['user']['id'])
