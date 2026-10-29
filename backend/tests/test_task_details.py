"""2.5真实数据库与接口回归：时段、有限重复、旧库、ICS和自动排程。"""
import hashlib
import json
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi import Depends, FastAPI, Header
from fastapi.testclient import TestClient
from icalendar import Calendar, Event
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.database import Base, get_db
from app.models.models import Analysis, Exam, IcsImportReceipt, Notification, Reminder, StudySetting, Task, User, UserProfile
from app.routers import ai, exams, features, study, tasks
from app.schemas.schemas import PlanItem
from app.services.calendar_io import parse_events
from app.services.plan_service import create_tasks_from_plan
from app.services.schema_upgrade import upgrade_schema
from app.services.task_details import occurrence_dates
from app.utils.security import get_current_user


class TaskDetailsTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.engine = create_engine('sqlite:///' + (Path(self.temp.name)/'tasks.db').as_posix(), connect_args={'check_same_thread': False})
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as db:
            db.add_all([User(id=1, username='owner', hashed_password='test'), User(id=2, username='peer', hashed_password='test')])
            db.add_all([Exam(id=1, user_id=1, subject='数学', exam_date=date.today()+timedelta(days=365)), Exam(id=2, user_id=2, subject='他人考试', exam_date=date.today()+timedelta(days=365)), Exam(id=3, user_id=1, subject='英语', exam_date=date.today()+timedelta(days=365))])
            db.add(StudySetting(user_id=1, daily_minutes=120))
            db.commit()
        app = FastAPI()
        def database():
            with Session(self.engine, autoflush=False) as db:
                yield db
        def current(x_user: int = Header(default=1), db=Depends(get_db)):
            return db.get(User, x_user)
        app.dependency_overrides[get_db] = database
        app.dependency_overrides[get_current_user] = current
        for name, module in [('tasks', tasks), ('exams', exams), ('ai', ai), ('features', features), ('study', study)]:
            app.include_router(module.router, prefix='/api/'+name)
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        self.client.close(); self.engine.dispose(); self.temp.cleanup()

    def payload(self, **changes):
        return {'exam_id':1, 'title':'极限练习', 'plan_date':date.today().isoformat(), 'estimated_minutes':60, 'priority':2, **changes}

    def call(self, method, path, body=None, status=200, headers=None):
        response = self.client.request(method, '/api'+path, json=body, headers=headers)
        self.assertEqual(response.status_code, status, response.text)
        return response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text

    def create(self, status=200, **changes):
        payload = self.payload()
        payload.update(changes)
        return self.call('POST', '/tasks', payload, status)

    def test_time_location_difficulty_and_detail_are_saved_and_read_back(self):
        created = self.create(start_time='09:05', end_time='10:20', estimated_minutes=1, location=' 图书馆三楼 ', difficulty='hard', detail=' 先做例题，再复盘错因 ')
        self.assertEqual((created['start_time'], created['end_time'], created['estimated_minutes']), ('09:05', '10:20', 75))
        self.assertEqual((created['location'], created['difficulty'], created['detail']), ('图书馆三楼', 'hard', '先做例题，再复盘错因'))
        self.assertEqual(created['created_count'], 1)
        read = self.call('GET', '/tasks')[0]
        self.assertEqual(read['start_time'], '09:05')
        with Session(self.engine) as db:
            row = db.get(Task, created['id'])
            self.assertEqual(row.start_time, time(9, 5))
            self.assertEqual(row.detail, created['detail'])

    def test_legacy_create_remains_untimed_and_partial_updates_preserve_fields(self):
        created = self.create()
        self.assertIsNone(created['start_time'])
        self.assertEqual(created['difficulty'], 'medium')
        updated = self.call('PUT', f"/tasks/{created['id']}", {'location': '自习室', 'start_time': '10:00', 'end_time': '10:45'})
        self.assertEqual(updated['estimated_minutes'], 45)
        updated = self.call('PUT', f"/tasks/{created['id']}", {'title': '修改本次'})
        self.assertEqual((updated['start_time'], updated['location']), ('10:00', '自习室'))
        cleared = self.call('PUT', f"/tasks/{created['id']}", {'start_time': None, 'end_time': None, 'location': '', 'detail': ''})
        self.assertIsNone(cleared['start_time']); self.assertEqual(cleared['location'], '')

    def test_invalid_times_fields_and_unbounded_repeats_write_nothing(self):
        cases = [dict(start_time='09:00'), dict(start_time='09:00', end_time='08:00'), dict(start_time='09:00', end_time='09:00'),
                 dict(start_time='09:00:30', end_time='10:00'), dict(start_time='09:00+08:00', end_time='10:00'), dict(start_time='24:00', end_time='10:00'),
                 dict(title='   '), dict(estimated_minutes=0), dict(difficulty='extreme'), dict(location='x'*121), dict(detail='x'*2001),
                 dict(repeat_rule='hourly'), dict(repeat_rule='daily'), dict(repeat_until=date.today().isoformat()), dict(repeat_group_id='forged'), dict(source='ai')]
        for case in cases:
            with self.subTest(case=case): self.create(status=422, **case)
        self.assertEqual(self.call('GET', '/tasks'), [])

    def test_preview_is_read_only_and_checks_every_date_against_shared_budget(self):
        day2 = (date.today()+timedelta(days=1)).isoformat()
        self.create(exam_id=3, plan_date=day2, estimated_minutes=100)
        with Session(self.engine) as db:
            before = {table.name: db.execute(table.select()).all() for table in Base.metadata.sorted_tables}
        payload = self.payload()
        payload.update(repeat_rule='daily', repeat_until=(date.today()+timedelta(days=2)).isoformat(), start_time='09:00', end_time='09:30')
        preview = self.call('POST', '/tasks/preview', payload)
        self.assertEqual((preview['count'], preview['total_minutes']), (3, 90))
        self.assertEqual(preview['warnings'][0]['date'], day2)
        self.assertEqual(preview['warnings'][0]['planned_minutes'], 130)
        with Session(self.engine) as db:
            self.assertEqual(before, {table.name: db.execute(table.select()).all() for table in Base.metadata.sorted_tables})

    def test_daily_weekdays_weekly_and_year_boundary_generate_exact_occurrences(self):
        self.assertEqual(occurrence_dates(date(2026,12,25), 'weekly', date(2027,1,8)), [date(2026,12,25), date(2027,1,1), date(2027,1,8)])
        start = date.today()
        friday = start + timedelta(days=(4-start.weekday()) % 7)
        row = self.create(plan_date=friday.isoformat(), repeat_rule='weekdays', repeat_until=(friday+timedelta(days=6)).isoformat(), start_time='08:00', end_time='08:20')
        self.assertEqual(row['created_count'], 5)
        items = self.call('GET', '/tasks')
        self.assertTrue(all(date.fromisoformat(t['plan_date']).weekday() < 5 for t in items))
        self.assertEqual(len({t['repeat_group_id'] for t in items}), 1)
        self.assertTrue(all(t['estimated_minutes'] == 20 for t in items))

    def test_repeat_limit_deadline_and_empty_weekday_range_are_rejected(self):
        start = date.today()
        self.create(status=422, repeat_rule='daily', repeat_until=(start+timedelta(days=180)).isoformat())
        self.create(status=422, repeat_rule='weekly', repeat_until=(start+timedelta(days=366)).isoformat())
        self.create(status=422, plan_date=(start+timedelta(days=366)).isoformat())
        saturday = start+timedelta(days=(5-start.weekday()) % 7)
        self.create(status=422, plan_date=saturday.isoformat(), repeat_rule='weekdays', repeat_until=(saturday+timedelta(days=1)).isoformat())
        self.assertEqual(self.call('GET', '/tasks'), [])

    def test_single_edit_does_not_change_siblings_and_moving_detaches_exception(self):
        created = self.create(repeat_rule='daily', repeat_until=(date.today()+timedelta(days=2)).isoformat(), location='原地点')
        ids = created['created_ids']
        self.call('PUT', f'/tasks/{ids[1]}', {'location': '本次地点', 'start_time': '14:00', 'end_time': '15:00'})
        rows = {t['id']: t for t in self.call('GET', '/tasks')}
        self.assertEqual(rows[ids[0]]['location'], '原地点'); self.assertEqual(rows[ids[2]]['location'], '原地点')
        self.assertEqual(rows[ids[1]]['repeat_group_id'], created['repeat_group_id'])
        self.call('PUT', f'/tasks/{ids[1]}', {'plan_date': (date.today()+timedelta(days=3)).isoformat()})
        moved = next(t for t in self.call('GET', '/tasks') if t['id'] == ids[1])
        self.assertIsNone(moved['repeat_group_id']); self.assertEqual(moved['repeat_rule'], 'none')
        self.call('PUT', f'/tasks/{ids[0]}', {'repeat_rule': 'weekly'}, status=422)

    def add_reminders(self, task_ids):
        with Session(self.engine) as db:
            for task_id in task_ids:
                task = db.get(Task, task_id)
                db.add(Reminder(user_id=1, target_type='task', target_id=task_id, target_created_at=task.created_at))
                db.add(Notification(user_id=1, target_type='task', target_id=task_id, target_created_at=task.created_at, occurrence_key=str(task_id), title='提醒', content='内容', due_at=datetime.now(), created_at=datetime.now()))
            db.commit()

    def test_delete_remaining_series_preserves_completed_earlier_and_other_groups(self):
        group = self.create(repeat_rule='daily', repeat_until=(date.today()+timedelta(days=3)).isoformat())
        ids = group['created_ids']
        self.add_reminders(ids)
        self.call('POST', f'/tasks/{ids[2]}/checkin')
        single = self.create(title='其他任务')
        self.assertEqual(self.call('DELETE', f'/tasks/{ids[1]}/series')['deleted'], 2)
        self.assertEqual({t['id'] for t in self.call('GET', '/tasks')}, {ids[0], ids[2], single['id']})
        with Session(self.engine) as db:
            self.assertEqual({r.target_id for r in db.query(Reminder)}, {ids[0], ids[2]})
            self.assertEqual({r.target_id for r in db.query(Notification)}, {ids[0], ids[2]})

    def test_single_delete_cleans_reminders_and_keeps_other_occurrences(self):
        group = self.create(repeat_rule='daily', repeat_until=(date.today()+timedelta(days=1)).isoformat())
        self.add_reminders(group['created_ids'])
        self.call('DELETE', f"/tasks/{group['id']}")
        self.assertEqual(len(self.call('GET', '/tasks')), 1)
        with Session(self.engine) as db:
            self.assertEqual(db.query(Reminder).count(), 1)

    def test_owner_isolation_in_preview_update_create_and_series_delete(self):
        row = self.create(repeat_rule='daily', repeat_until=(date.today()+timedelta(days=1)).isoformat())
        peer = {'X-User': '2'}
        self.assertEqual(self.call('GET', '/tasks', headers=peer), [])
        self.call('POST', '/tasks', self.payload(), 404, peer)
        self.call('PUT', f"/tasks/{row['id']}", {'location': 'forged'}, 404, peer)
        self.call('DELETE', f"/tasks/{row['id']}/series", status=404, headers=peer)
        self.call('POST', '/tasks/preview', {**self.payload(exam_id=2), 'exclude_task_id': row['id']}, 404, peer)
        self.assertEqual(len(self.call('GET', '/tasks')), 2)

    def test_failed_batch_commit_leaves_no_partial_series(self):
        with patch.object(Session, 'commit', side_effect=RuntimeError('injected failure')):
            self.create(status=500, repeat_rule='daily', repeat_until=(date.today()+timedelta(days=2)).isoformat())
        self.assertEqual(self.call('GET', '/tasks'), [])
        self.assertEqual(self.create(repeat_rule='daily', repeat_until=(date.today()+timedelta(days=2)).isoformat())['created_count'], 3)

    def test_incomplete_or_null_update_rejects_without_overwriting_existing(self):
        task = self.create(start_time='09:00', end_time='10:00', location='保留')
        for body in ({'start_time': None}, {'start_time': '11:00'}, {'location': None}, {'estimated_minutes': None}, {'title': ' '}):
            self.call('PUT', f"/tasks/{task['id']}", body, 422)
        unchanged = self.call('GET', '/tasks')[0]
        self.assertEqual((unchanged['start_time'], unchanged['end_time'], unchanged['location']), ('09:00','10:00','保留'))

    def test_additive_legacy_migration_preserves_task_data_and_is_repeatable(self):
        original = self.create(title='历史任务', estimated_minutes=77)
        self.call('POST', f"/tasks/{original['id']}/checkin")
        fields = ('start_time','end_time','location','difficulty','detail','repeat_rule','repeat_until','repeat_group_id')
        with self.engine.begin() as conn:
            conn.execute(text('DROP INDEX ix_tasks_repeat_group_id'))
            for field in fields: conn.execute(text('ALTER TABLE tasks DROP COLUMN '+field))
            before = conn.execute(text('SELECT id,title,plan_date,estimated_minutes,is_done,done_at FROM tasks')).all()
        upgrade_schema(self.engine); upgrade_schema(self.engine)
        with self.engine.connect() as conn:
            self.assertEqual(before, conn.execute(text('SELECT id,title,plan_date,estimated_minutes,is_done,done_at FROM tasks')).all())
            self.assertTrue(set(fields).issubset({c['name'] for c in inspect(conn).get_columns('tasks')}))
        migrated = self.call('GET', '/tasks')[0]
        self.assertIsNone(migrated['start_time']); self.assertEqual(migrated['difficulty'], 'medium'); self.assertTrue(migrated['is_done'])

    def test_fixed_ai_task_survives_regeneration_and_rescheduling(self):
        with Session(self.engine) as db:
            fixed = Task(user_id=1, exam_id=1, title='极限', plan_date=date.today(), estimated_minutes=60, source='ai', start_time=time(9), end_time=time(10), location='固定地点', difficulty='hard', detail='原内容')
            db.add(fixed); db.commit(); fixed_id = fixed.id
            result = create_tasks_from_plan(db, 1, 1, 1, [PlanItem(day=1, date=date.today().isoformat(), title='极限', estimated_minutes=150, detail='新内容')])
            self.assertTrue(result['applied'])
            db.expire_all(); preserved = db.get(Task, fixed_id)
            self.assertEqual((preserved.start_time, preserved.end_time, preserved.location, preserved.detail), (time(9), time(10), '固定地点', '原内容'))
            self.assertEqual(sum(t.estimated_minutes for t in db.query(Task)), 150)
        preview = self.call('GET', '/study/plan/preview')
        self.assertNotIn(fixed_id, {a['task_id'] for a in preview['assignments']})
        self.call('POST', '/study/plan/confirm', {'fingerprint': preview['fingerprint']})
        self.assertEqual(next(t for t in self.call('GET', '/tasks') if t['id'] == fixed_id)['start_time'], '09:00')

    def test_time_change_invalidates_plan_snapshot_even_when_duration_is_unchanged(self):
        row = self.create(start_time='09:00', end_time='10:00')
        before = self.call('GET', '/study/plan/preview')
        self.call('PUT', f"/tasks/{row['id']}", {'start_time':'11:00','end_time':'12:00'})
        self.call('POST', '/study/plan/confirm', {'fingerprint':before['fingerprint']}, 409)

    def test_feedback_replan_preserves_fixed_task_and_counts_its_minutes(self):
        with Session(self.engine) as db:
            profile = UserProfile(user_id=1, exam_id=1, target='medium', learning_status='medium', daily_hours=2, available_days=5, is_complete=True)
            db.add(profile); db.flush()
            analysis = Analysis(user_id=1, exam_id=1, profile_id=profile.id, result_json=json.dumps({'course':'数学','knowledge_points':[{'name':'积分','weight':.8}],'review_plan':[]}))
            db.add(analysis); db.flush()
            fixed = Task(user_id=1, exam_id=1, analysis_id=analysis.id, title='积分', plan_date=date.today(), estimated_minutes=60, start_time=time(9), end_time=time(10), source='ai', location='固定地点')
            db.add_all([fixed, Task(user_id=1, exam_id=1, analysis_id=analysis.id, title='自由复习', plan_date=date.today(), estimated_minutes=180, source='ai', detail='保留内容')])
            db.commit(); fixed_id = fixed.id
        preview = self.call('POST','/ai/analyses/1/replan',{'apply':False})
        self.assertEqual(sum(p['estimated_minutes'] for p in preview['plan']),240)
        self.assertTrue(any('固定时段' in p['detail'] for p in preview['plan']))
        self.call('POST','/ai/analyses/1/replan',{'apply':True,'fingerprint':preview['fingerprint']})
        row = next(t for t in self.call('GET','/tasks') if t['id']==fixed_id)
        self.assertEqual((row['start_time'],row['location']),('09:00','固定地点'))
        latest = self.call('GET','/ai/analyses/1')['result']
        self.assertEqual(sum(p['estimated_minutes'] for p in latest['review_plan']),240)

    def test_future_manual_and_repeating_days_remain_visible_in_global_preview(self):
        start = date.today()+timedelta(days=1)
        self.create(plan_date=start.isoformat(),repeat_rule='daily',repeat_until=(start+timedelta(days=2)).isoformat())
        preview = self.call('GET','/study/plan/preview')
        self.assertEqual(len(preview['days']),3)
        self.assertEqual(sum(d['minutes'] for d in preview['days']),180)

    def test_reverse_schedule_preserves_fixed_and_completed_tasks_without_double_counting(self):
        today = date.today()
        with Session(self.engine) as db:
            db.get(Exam,1).exam_date = today+timedelta(days=3)
            fixed = Task(user_id=1,exam_id=1,title='【倒推】固定复习',plan_date=today+timedelta(days=1),
                         estimated_minutes=60,source='ai',start_time=time(9),end_time=time(10),location='固定地点')
            done = Task(user_id=1,exam_id=1,title='【倒推】已完成',plan_date=today,estimated_minutes=60,source='ai',is_done=True)
            db.add_all([fixed,done]); db.commit(); kept = {fixed.id,done.id}
        result = self.call('POST','/exams/1/generate-schedule',{'daily_minutes':60,'start_date':today.isoformat()})
        self.assertEqual(result['total_minutes'],60)
        rows = self.call('GET','/tasks')
        self.assertTrue(kept.issubset({t['id'] for t in rows}))
        self.assertEqual(sum(t['estimated_minutes'] for t in rows),180)
        self.assertEqual(next(t for t in rows if t['id']==fixed.id)['location'],'固定地点')

    def test_relief_reports_fixed_time_instead_of_moving_it(self):
        row = self.create(start_time='09:00', end_time='10:30')
        preview = self.call('GET', '/features/relief?option=lighten')
        self.assertTrue(preview['conflicts'])
        self.assertNotIn(row['id'], {m['task_id'] for m in preview['moves']})

    def make_calendar(self, starts, title='复习', detail='内容', location='自习室'):
        calendar = Calendar(); calendar.add('version','2.0')
        for start in starts:
            event = Event(); event.add('summary',title); event.add('dtstart', start); event.add('dtend',start+timedelta(minutes=30)); event.add('location',location); event.add('description',detail); calendar.add_component(event)
        return calendar.to_ical()

    def test_ics_same_title_on_different_times_is_preserved_and_saved(self):
        starts = [datetime.combine(date.today(), time(9)), datetime.combine(date.today(), time(14))]
        content = self.make_calendar(starts)
        preview = self.client.post('/api/exams/import-ics', data={'exam_id':1}, files={'file':('tasks.ics',content,'text/calendar')})
        self.assertEqual(preview.status_code,200,preview.text)
        self.assertEqual(preview.json()['count'],2)
        confirmed = self.call('POST','/exams/import-ics/confirm',{'preview_token':preview.json()['preview_token']})
        self.assertEqual(confirmed['imported'],2)
        rows = self.call('GET','/tasks')
        self.assertEqual({t['start_time'] for t in rows},{'09:00','14:00'})
        self.assertTrue(all(t['location']=='自习室' and t['detail']=='内容' for t in rows))

    def test_ics_export_preserves_real_times_and_untimed_placeholder_semantics(self):
        timed = self.create(start_time='13:10',end_time='14:25',location='A;B',detail='原文\n第二行')
        self.create(title='未定时', estimated_minutes=1440, detail='长'*2000)
        response = self.client.get('/api/exams/export-ics')
        self.assertEqual(response.status_code,200)
        events = Calendar.from_ical(response.content).walk('VEVENT')
        event = next(e for e in events if str(e.get('UID','')).startswith('task-'+str(timed['id'])+'-'))
        self.assertEqual(event.decoded('DTSTART').hour,5)
        self.assertEqual(event.decoded('DTSTART').minute,10)
        self.assertEqual(str(event['LOCATION']),'A;B')
        parsed,_ = parse_events(response.text)
        original = next(e for e in parsed if '极限练习' in e['title'])
        untimed = next(e for e in parsed if '未定时' in e['title'])
        self.assertEqual(original['detail'],'原文\n第二行')
        self.assertIsNone(untimed['start_time']); self.assertEqual(untimed['minutes'],1440); self.assertEqual(len(untimed['detail']),2000)

    def test_ics_old_receipt_prevents_duplicates_after_time_upgrade(self):
        content = self.make_calendar([datetime.combine(date.today(),time(9))])
        with Session(self.engine) as db:
            exam = db.get(Exam,1)
            old_events = [dict(title='复习', day=date.today().isoformat(), minutes=30)]
            key = hashlib.sha256(json.dumps([1,1,exam.created_at.isoformat(),old_events],sort_keys=True).encode()).hexdigest()
            db.add(IcsImportReceipt(id=key,user_id=1,exam_id=1,imported=1)); db.commit()
        response = self.client.post('/api/exams/import-ics',data={'exam_id':1},files={'file':('tasks.ics',content,'text/calendar')})
        self.assertEqual(response.status_code,200,response.text)
        self.assertTrue(response.json()['already_imported']); self.assertIn('旧版',response.json()['note'])
        self.assertTrue(self.call('POST','/exams/import-ics/confirm',{'preview_token':response.json()['preview_token']})['already_imported'])
        self.assertEqual(self.call('GET','/tasks'),[])

    def test_ics_cross_midnight_and_seconds_are_rejected_explicitly(self):
        for start in (datetime.combine(date.today(),time(23,45)),datetime.combine(date.today(),time(9,0,30))):
            content = self.make_calendar([start])
            response = self.client.post('/api/exams/import-ics',data={'exam_id':1},files={'file':('tasks.ics',content,'text/calendar')})
            self.assertEqual(response.status_code,400,response.text)


if __name__ == '__main__': unittest.main()
