"""时段重叠的接口、真实 SQLite 事务、并发与 ICS 边界。"""
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta
from threading import Barrier

from sqlalchemy.orm import Session

from app.database import Base
from app.models.models import Task
from app.services.task_conflicts import find_overlaps
import test_task_details as fixtures


class TaskConflictTests(unittest.TestCase):
    setUp = fixtures.TaskDetailsTests.setUp
    tearDown = fixtures.TaskDetailsTests.tearDown
    payload = fixtures.TaskDetailsTests.payload
    call = fixtures.TaskDetailsTests.call
    create = fixtures.TaskDetailsTests.create
    make_calendar = fixtures.TaskDetailsTests.make_calendar

    def test_intersection_containment_identical_and_adjacent_boundaries(self):
        first = self.create(start_time='09:00',end_time='10:00')
        for start,end,minutes in [('09:30','10:30',30),('08:30','09:15',15),('08:00','11:00',60),('09:15','09:45',30),('09:00','10:00',60)]:
            preview = self.call('POST','/tasks/preview',self.payload(start_time=start,end_time=end))
            self.assertFalse(preview['can_save']); self.assertEqual(preview['overlaps'][0]['overlap_minutes'],minutes)
            self.assertIn(first['id'],[preview['overlaps'][0]['first']['task_id'],preview['overlaps'][0]['second']['task_id']])
        for start,end in [('08:00','09:00'),('10:00','11:00')]:
            self.assertTrue(self.call('POST','/tasks/preview',self.payload(start_time=start,end_time=end))['can_save'])
            self.create(start_time=start,end_time=end)

    def test_preview_and_scan_are_read_only_and_have_cross_course_details(self):
        self.create(exam_id=3,title='英语听力',start_time='09:00',end_time='10:00')
        with Session(self.engine) as db:
            before = {t.name:db.execute(t.select()).all() for t in Base.metadata.sorted_tables}
        preview = self.call('POST','/tasks/preview',self.payload(start_time='09:30',end_time='10:30'))
        self.assertFalse(preview['can_save']); self.assertEqual(preview['overlaps'][0]['first']['subject'],'英语')
        self.call('GET','/tasks/conflicts')
        with Session(self.engine) as db:
            self.assertEqual(before,{t.name:db.execute(t.select()).all() for t in Base.metadata.sorted_tables})

    def test_direct_create_cannot_bypass_preview_or_partially_save_repeat_batch(self):
        day2 = date.today()+timedelta(days=1)
        original = self.create(exam_id=3,plan_date=day2.isoformat(),start_time='09:00',end_time='10:00')
        error = self.create(status=409,repeat_rule='daily',repeat_until=(day2+timedelta(days=1)).isoformat(),start_time='09:30',end_time='10:30')
        self.assertIn('重叠',error['detail']['message']); self.assertEqual(len(error['detail']['overlaps']),1)
        self.assertEqual([t['id'] for t in self.call('GET','/tasks')],[original['id']])

    def test_update_merges_original_times_excludes_self_and_preserves_on_rejection(self):
        first = self.create(start_time='09:00',end_time='10:00',repeat_rule='daily',repeat_until=(date.today()+timedelta(days=1)).isoformat())
        second = self.create(exam_id=3,start_time='10:00',end_time='11:00')
        self.assertTrue(self.call('POST','/tasks/preview',self.payload(start_time='09:00',end_time='10:00',exclude_task_id=first['id']))['can_save'])
        self.call('PUT',f"/tasks/{first['id']}",{'end_time':'10:15'},409)
        read = next(t for t in self.call('GET','/tasks') if t['id']==first['id'])
        self.assertEqual((read['end_time'],read['repeat_group_id']),('10:00',first['repeat_group_id']))
        self.call('PUT',f"/tasks/{second['id']}",{'plan_date':(date.today()+timedelta(days=1)).isoformat(),'start_time':'09:30','end_time':'10:30'},409)
        self.call('PUT',f"/tasks/{second['id']}",{'start_time':None,'end_time':None})
        self.call('PUT',f"/tasks/{first['id']}",{'end_time':'10:15'})

    def test_completed_times_occupy_space_untimed_and_other_dates_do_not(self):
        first = self.create(start_time='09:00',end_time='10:00')
        self.call('POST',f"/tasks/{first['id']}/checkin")
        self.create(status=409,start_time='09:30',end_time='10:30')
        self.create(title='未定时',estimated_minutes=1440)
        self.create(plan_date=(date.today()+timedelta(days=1)).isoformat(),start_time='09:00',end_time='10:00')
        self.assertEqual(self.call('GET','/tasks/conflicts')['count'],0)

    def test_other_users_are_isolated_and_cannot_be_excluded(self):
        peer = self.call('POST','/tasks',self.payload(exam_id=2,title='他人私有内容',start_time='09:00',end_time='10:00'),headers={'x-user':'2'})
        mine = self.create(start_time='09:00',end_time='10:00')
        result = self.call('POST','/tasks/check-conflict',self.payload(start_time='09:30',end_time='10:30',exclude_task_id=mine['id']))
        self.assertEqual(result['overlaps'],[])
        self.call('POST','/tasks/check-conflict',self.payload(exclude_task_id=peer['id']),404)
        self.assertNotIn('他人私有内容',str(self.call('GET','/tasks/conflicts')))

    def test_precheck_uses_actual_minutes_shared_budget_and_rejects_invalid_pairs(self):
        self.create(estimated_minutes=100)
        result = self.call('POST','/tasks/check-conflict',self.payload(estimated_minutes=1,start_time='09:00',end_time='09:30',daily_limit_minutes=1440))
        self.assertEqual((result['planned_minutes'],result['limit_minutes']),(130,120)); self.assertTrue(result['budget_exceeded'])
        for values in [dict(start_time='09:00'),dict(start_time='10:00',end_time='09:00'),dict(start_time='09:00:30',end_time='10:00')]:
            self.call('POST','/tasks/check-conflict',self.payload(**values),422)

    def test_legacy_overlaps_remain_visible_and_metadata_only_edits_are_possible(self):
        first = self.create(start_time='09:00',end_time='10:00')
        with Session(self.engine) as db:
            db.add(Task(user_id=1,exam_id=3,title='旧时段',plan_date=date.today(),start_time=time(9,30),end_time=time(10,30),estimated_minutes=60,source='manual')); db.commit()
        scan = self.call('GET','/tasks/conflicts?plan_date='+date.today().isoformat())
        self.assertEqual(scan['count'],1); self.assertEqual(scan['overlaps'][0]['overlap_minutes'],30)
        preview = self.call('POST','/tasks/preview',self.payload(start_time='09:00',end_time='10:00',exclude_task_id=first['id']))
        self.assertTrue(preview['can_save']); self.assertEqual(len(preview['overlaps']),1)
        self.call('PUT',f"/tasks/{first['id']}",{'location':'补充地点'})
        plan = self.call('GET','/study/plan/preview'); self.assertTrue(any('时段重叠' in c['reason'] for c in plan['conflicts']))
        self.call('PUT',f"/tasks/{first['id']}",{'start_time':'08:30','end_time':'09:30'})
        self.assertEqual(self.call('GET','/tasks/conflicts')['count'],0)

    def test_preview_race_is_rechecked_on_create_and_update(self):
        payload = self.payload(start_time='09:00',end_time='10:00')
        self.assertTrue(self.call('POST','/tasks/preview',payload)['can_save'])
        self.create(exam_id=3,start_time='09:30',end_time='10:30')
        self.call('POST','/tasks',payload,409)
        free = self.create(start_time='11:00',end_time='12:00')
        self.call('PUT',f"/tasks/{free['id']}",{'start_time':'09:00','end_time':'10:00'},409)

    def test_concurrent_cross_course_creates_only_save_one_conflicting_task(self):
        barrier = Barrier(2)
        def create(exam_id):
            barrier.wait(timeout=5)
            return self.client.post('/api/tasks',json=self.payload(exam_id=exam_id,start_time='09:00',end_time='10:00')).status_code
        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(create,[1,3]))
        self.assertEqual(sorted(statuses),[200,409]); self.assertEqual(len(self.call('GET','/tasks')),1)

    def import_preview(self, starts):
        content = self.make_calendar(starts)
        response = self.client.post('/api/exams/import-ics',data={'exam_id':1},files={'file':('conflicts.ics',content,'text/calendar')})
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def test_ics_detects_batch_internal_overlap_and_confirmation_saves_nothing(self):
        preview = self.import_preview([datetime.combine(date.today(),time(9)),datetime.combine(date.today(),time(9,15))])
        overlap = next(c for c in preview['conflicts'] if c.get('kind')=='time_overlap')
        self.assertEqual(overlap['overlap_minutes'],15)
        self.call('POST','/exams/import-ics/confirm',{'preview_token':preview['preview_token']},409)
        self.assertEqual(self.call('GET','/tasks'),[])

    def test_ics_detects_existing_cross_course_and_accepts_adjacent_events(self):
        row = self.create(exam_id=3,start_time='09:00',end_time='09:30')
        conflict = self.import_preview([datetime.combine(date.today(),time(9,15))])
        self.assertEqual(conflict['conflicts'][0]['kind'],'time_overlap')
        self.assertIn(row['id'],[conflict['conflicts'][0]['first']['task_id'],conflict['conflicts'][0]['second']['task_id']])
        preview = self.import_preview([datetime.combine(date.today(),time(9,30)),datetime.combine(date.today(),time(10))])
        self.assertEqual(preview['conflicts'],[])
        self.call('POST','/exams/import-ics/confirm',{'preview_token':preview['preview_token']})
        self.assertEqual(self.call('GET','/tasks/conflicts')['count'],0)

    def test_ics_stale_preview_rejects_new_conflict(self):
        preview = self.import_preview([datetime.combine(date.today(),time(9))])
        self.create(exam_id=3,start_time='09:10',end_time='09:40')
        self.call('POST','/exams/import-ics/confirm',{'preview_token':preview['preview_token']},409)
        self.assertEqual(len(self.call('GET','/tasks')),1)


if __name__=='__main__': unittest.main()
