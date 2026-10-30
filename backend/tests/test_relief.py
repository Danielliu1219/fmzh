"""7.7 半天粒度、边界、快照、事务和账号隔离。"""
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta
from threading import Barrier
from unittest.mock import patch

from sqlalchemy.orm import Session

from app.models.models import Exam, StudySetting, Task
from app.services.relief import distribute
import test_task_details as fixtures

NOW=datetime(2026,10,30,8)
TODAY=NOW.date().isoformat()
EXAMS={1:dict(exam_date='2026-11-02'),3:dict(exam_date='2026-11-03')}


def task(id=1, minutes=60, **kw):
    return dict(id=id,title=f'任务{id}',exam_id=1,estimated_minutes=minutes,priority=2,is_done=False,
                plan_date=TODAY,start_time=None,end_time=None,**kw)


class ReliefAlgorithmTests(unittest.TestCase):
    def test_afternoon_rest_keeps_morning_work_and_exact_minutes(self):
        rows=[task(1),task(2),task(3)]
        plan=distribute(rows,EXAMS,240,NOW,'halfday','afternoon')
        self.assertFalse(plan['conflicts'])
        self.assertEqual(plan['today_capacity'],120)
        self.assertEqual([(r['start_time'],r['end_time']) for r in plan['retained']],[('08:05','09:05'),('09:05','10:05')])
        self.assertEqual(plan['moves'][2]['to_date'],'2026-10-31')
        self.assertEqual(sum(m['minutes'] for m in plan['moves']),180)
        self.assertTrue(all(r['estimated_minutes']==60 and r['start_time'] is None for r in rows))

    def test_morning_rest_starts_at_noon_and_preserves_completed_history(self):
        done=task(2,45);done.update(is_done=True,start_time='08:00',end_time='08:45')
        plan=distribute([task(1),done],EXAMS,240,NOW,'halfday','morning')
        self.assertFalse(plan['conflicts'])
        self.assertEqual(plan['retained'][0]['start_time'],'12:00')
        self.assertEqual(plan['completed_minutes'],45)
        self.assertEqual([m['task_id'] for m in plan['moves']],[1])

    def test_fixed_rest_intersection_and_noon_boundaries(self):
        for a,b,conflict in [('11:00','12:00',False),('12:00','13:00',True),('11:30','12:30',True)]:
            fixed=task(1);fixed.update(start_time=a,end_time=b)
            plan=distribute([fixed],EXAMS,240,NOW,'halfday','afternoon')
            self.assertEqual(bool(plan['conflicts']),conflict)
            self.assertEqual(plan['moves'],[])

    def test_continuous_gap_is_required_even_when_budget_remains(self):
        fixed=task(2,30);fixed.update(start_time='11:00',end_time='11:30')
        now=NOW.replace(hour=10,minute=30)
        row=task(1,40)
        plan=distribute([row,fixed],{1:dict(exam_date=TODAY)},240,now,'halfday','afternoon')
        self.assertTrue(plan['conflicts'])
        self.assertEqual(plan['moves'],[])

    def test_expired_half_and_late_evening_do_not_invent_past_time(self):
        plan=distribute([task()],EXAMS,240,NOW.replace(hour=13),'halfday','morning')
        self.assertTrue(plan['conflicts'])
        plan=distribute([task()],EXAMS,240,NOW.replace(hour=23,minute=58),'halfday','afternoon')
        self.assertEqual(plan['retained'],[])
        self.assertEqual(plan['moves'][0]['to_date'],'2026-10-31')

    def test_completed_over_half_capacity_does_not_require_rewriting_history(self):
        done=task(2,180);done['is_done']=True
        plan=distribute([task(),done],EXAMS,240,NOW,'halfday')
        self.assertFalse(plan['conflicts'])
        self.assertEqual(plan['moves'][0]['to_date'],'2026-10-31')
        self.assertEqual(plan['completed_minutes'],180)

    def test_oversized_deadline_missing_exam_and_fixed_past_are_explicit(self):
        for rows,exams in [([task(1,300)],EXAMS),([task()],{}),([task()],{1:dict(exam_date='2026-10-29')})]:
            plan=distribute(rows,exams,240,NOW,'halfday')
            self.assertTrue(plan['conflicts']);self.assertEqual(plan['moves'],[])
        fixed=task();fixed.update(plan_date='2026-10-29',start_time='09:00',end_time='10:00')
        self.assertIn('固定时段已过',distribute([fixed],EXAMS,240,NOW,'halfday')['conflicts'][0]['reason'])

    def test_frozen_future_budget_and_overlaps_are_reported(self):
        a,b=task(1,180),task(2,180)
        for row in (a,b):row.update(plan_date='2026-10-31',start_time='09:00',end_time='12:00')
        plan=distribute([a,b],EXAMS,240,NOW,'halfday')
        self.assertTrue(any('预算' in c['reason'] for c in plan['conflicts']))
        self.assertTrue(any('重叠' in c['reason'] for c in plan['conflicts']))


class ReliefApiTests(unittest.TestCase):
    tearDown=fixtures.TaskDetailsTests.tearDown
    payload=fixtures.TaskDetailsTests.payload
    call=fixtures.TaskDetailsTests.call
    create=fixtures.TaskDetailsTests.create
    def setUp(self):
        fixtures.TaskDetailsTests.setUp(self)
        self.now=datetime.combine(date.today(),time(8))
        self.clock=patch('app.services.relief.clock_now',return_value=self.now);self.clock.start();self.addCleanup(self.clock.stop)
        with Session(self.engine) as db:
            db.get(StudySetting,1).daily_minutes=240;db.commit()

    def preview(self,half='afternoon'):
        return self.call('GET','/features/relief?option=halfday&half='+half)

    def confirm(self,plan,status=200,headers=None):
        return self.call('POST','/features/relief/apply',dict(option=plan['option'],half=plan['half'] or 'afternoon',fingerprint=plan['fingerprint'],preview_at=plan['preview_at']),status,headers)

    def test_preview_readonly_save_times_details_and_readback(self):
        row=self.create(location='三楼',difficulty='hard',detail='保留内容')
        before=self.call('GET','/tasks')
        plan=self.preview();self.assertEqual(before,self.call('GET','/tasks'))
        self.confirm(plan)
        saved=self.call('GET','/tasks')[0]
        self.assertEqual((saved['id'],saved['start_time'],saved['end_time'],saved['estimated_minutes']),(row['id'],'08:05','09:05',60))
        self.assertEqual((saved['location'],saved['difficulty'],saved['detail'],saved['source']),('三楼','hard','保留内容','manual'))
        self.confirm(plan,409)

    def test_snapshot_invalidates_task_budget_exam_or_day_change(self):
        row=self.create()
        plan=self.preview()
        self.call('PUT',f"/tasks/{row['id']}",{'detail':'另一页面修改'})
        self.confirm(plan,409)
        plan=self.preview()
        with Session(self.engine) as db:db.get(StudySetting,1).daily_minutes=180;db.commit()
        self.confirm(plan,409)
        plan=self.preview()
        with Session(self.engine) as db:db.get(Exam,1).exam_date+=timedelta(days=1);db.commit()
        self.confirm(plan,409)
        plan=self.preview()
        with patch('app.services.relief.clock_now',return_value=self.now+timedelta(days=1)):self.confirm(plan,409)

    def test_expiry_future_and_start_time_passed_reject(self):
        self.create();plan=self.preview()
        for offset in (timedelta(minutes=11),timedelta(seconds=-1),timedelta(minutes=6)):
            with patch('app.services.relief.clock_now',return_value=self.now+offset):self.confirm(plan,409)
        self.call('POST','/features/relief/apply',{'option':'halfday'},409)
        self.call('GET','/features/relief?option=bad',status=422)
        self.call('GET','/features/relief?option=halfday&half=bad',status=422)

    def test_conflicts_block_all_changes_and_completed_tasks_stay(self):
        fixed=self.create(start_time='14:00',end_time='15:00')
        row=self.create()
        done=self.create(estimated_minutes=180)
        self.call('POST',f"/tasks/{done['id']}/checkin")
        before=self.call('GET','/tasks');plan=self.preview();self.assertTrue(plan['conflicts'])
        self.confirm(plan,409);self.assertEqual(before,self.call('GET','/tasks'))
        self.assertNotIn(fixed['id'],{m['task_id'] for m in plan['moves']})

    def test_ownership_and_new_task_race(self):
        self.create();plan=self.preview()
        self.confirm(plan,409,{'x-user':'2'})
        self.create(title='新任务',estimated_minutes=45)
        self.confirm(plan,409)
        self.assertTrue(all(t['start_time'] is None for t in self.call('GET','/tasks')))

    def test_repeat_detaches_only_moved_occurrence_and_rollback_is_atomic(self):
        # 超过半日容量，整个实例后移，不合并或删除后续重复项。
        row=self.create(estimated_minutes=150,repeat_rule='daily',repeat_until=(date.today()+timedelta(days=1)).isoformat())
        plan=self.preview()
        self.assertFalse(plan['conflicts'])
        before=self.call('GET','/tasks')
        with patch('sqlalchemy.orm.Session.commit',side_effect=RuntimeError('simulated failure')):self.confirm(plan,500)
        self.assertEqual(before,self.call('GET','/tasks'))
        self.confirm(plan)
        rows=self.call('GET','/tasks')
        self.assertEqual(len(rows),2)
        changed=next(t for t in rows if t['id']==row['id'])
        self.assertIsNone(changed['repeat_group_id']);self.assertEqual(sum(t['estimated_minutes'] for t in rows),300)
        self.assertEqual(next(t for t in rows if t['id']!=row['id'])['repeat_group_id'],row['repeat_group_id'])

    def test_two_confirmations_are_serialized(self):
        self.create();plan=self.preview();barrier=Barrier(2)
        body=dict(option=plan['option'],half=plan['half'],fingerprint=plan['fingerprint'],preview_at=plan['preview_at'])
        def confirm(_):
            barrier.wait();return self.client.post('/api/features/relief/apply',json=body).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:statuses=list(pool.map(confirm,range(2)))
        self.assertEqual(sorted(statuses),[200,409])
        self.assertEqual(self.call('GET','/tasks')[0]['start_time'],'08:05')
