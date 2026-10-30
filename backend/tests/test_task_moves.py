"""日历移动：真实事务、时长、快照、账号隔离和并发。"""
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from threading import Barrier
from unittest.mock import patch

from sqlalchemy.orm import Session

from app.database import Base
from app.models.models import Task
import test_task_details as fixtures


class TaskMoveTests(unittest.TestCase):
    setUp=fixtures.TaskDetailsTests.setUp
    tearDown=fixtures.TaskDetailsTests.tearDown
    payload=fixtures.TaskDetailsTests.payload
    call=fixtures.TaskDetailsTests.call
    create=fixtures.TaskDetailsTests.create

    def move_body(self,task,**changes):
        return dict(plan_date=task['plan_date'],fingerprint=task['move_fingerprint'],**changes)

    def moved(self,task,body,status=200,preview=False,headers=None):
        return self.call('POST',f"/tasks/{task['id']}/move"+('/preview' if preview else ''),body,status,headers)

    def test_response_contains_stable_snapshot_and_edit_invalidates_it(self):
        row=self.create()
        self.assertEqual(len(row['move_fingerprint']),64)
        self.assertEqual(row['move_fingerprint'],self.call('GET','/tasks')[0]['move_fingerprint'])
        edited=self.call('PUT',f"/tasks/{row['id']}",{'location':'改地点'})
        self.assertNotEqual(edited['move_fingerprint'],row['move_fingerprint'])
        self.moved(row,self.move_body(row,start_time='09:00'),409)

    def test_preview_has_no_writes_and_derives_end_from_existing_minutes(self):
        row=self.create(estimated_minutes=75,location='自习室',difficulty='hard',detail='复盘错题')
        with Session(self.engine) as db: before={t.name:db.execute(t.select()).all() for t in Base.metadata.sorted_tables}
        preview=self.moved(row,self.move_body(row,start_time='09:15'),preview=True)
        self.assertEqual((preview['candidate']['start_time'],preview['candidate']['end_time'],preview['candidate']['estimated_minutes']),('09:15','10:30',75))
        with Session(self.engine) as db: self.assertEqual(before,{t.name:db.execute(t.select()).all() for t in Base.metadata.sorted_tables})

    def test_timed_move_preserves_duration_and_metadata_and_round_trips(self):
        row=self.create(start_time='09:05',end_time='10:20',location='固定地点',difficulty='hard',detail='原内容')
        result=self.moved(row,self.move_body(row,start_time='13:15'))
        self.assertEqual((result['start_time'],result['end_time'],result['estimated_minutes']),('13:15','14:30',75))
        self.assertEqual((result['location'],result['difficulty'],result['detail']),('固定地点','hard','原内容'))
        self.assertEqual(result,self.call('GET','/tasks')[0])

    def test_date_only_move_keeps_clock_and_repeat_siblings_unchanged(self):
        row=self.create(start_time='09:00',end_time='09:30',repeat_rule='daily',repeat_until=(date.today()+timedelta(days=1)).isoformat())
        body={**self.move_body(row), 'plan_date':(date.today()+timedelta(days=2)).isoformat()}
        result=self.moved(row,body)
        self.assertEqual((result['start_time'],result['end_time'],result['repeat_rule'],result['repeat_group_id']),('09:00','09:30','none',None))
        sibling=next(t for t in self.call('GET','/tasks') if t['id']==row['created_ids'][1])
        self.assertEqual((sibling['plan_date'],sibling['repeat_group_id']),((date.today()+timedelta(days=1)).isoformat(),row['repeat_group_id']))

    def test_same_day_time_move_only_changes_this_repeat_instance(self):
        row=self.create(start_time='09:00',end_time='09:30',repeat_rule='daily',repeat_until=(date.today()+timedelta(days=1)).isoformat())
        result=self.moved(row,self.move_body(row,start_time='11:00'))
        self.assertEqual(result['repeat_group_id'],row['repeat_group_id'])
        sibling=next(t for t in self.call('GET','/tasks') if t['id']==row['created_ids'][1])
        self.assertEqual(sibling['start_time'],'09:00')

    def test_clearing_time_keeps_minutes_and_omitted_start_keeps_untimed(self):
        row=self.create(start_time='09:00',end_time='10:15')
        result=self.moved(row,self.move_body(row,start_time=None))
        self.assertIsNone(result['start_time']); self.assertIsNone(result['end_time']); self.assertEqual(result['estimated_minutes'],75)
        result=self.moved(result,{**self.move_body(result),'plan_date':(date.today()+timedelta(days=1)).isoformat()})
        self.assertIsNone(result['start_time']); self.assertEqual(result['estimated_minutes'],75)

    def test_completed_and_cross_user_moves_reject_and_leave_history(self):
        row=self.create(start_time='09:00',end_time='10:00')
        self.moved(row,self.move_body(row,start_time='11:00'),404,headers={'x-user':'2'})
        done=self.call('POST',f"/tasks/{row['id']}/checkin")
        self.moved(done,self.move_body(done,start_time='11:00'),409)
        self.assertEqual(self.call('GET','/tasks')[0],done)

    def test_invalid_or_forged_payload_and_exam_deadline_reject(self):
        row=self.create()
        for changes in [dict(fingerprint='wrong'),dict(start_time='09:00:30'),dict(start_time='24:00'),dict(end_time='10:00'),dict(estimated_minutes=1),dict(title='伪造'),dict(plan_date=(date.today()+timedelta(days=366)).isoformat())]:
            self.moved(row,{**self.move_body(row),**changes},422)
        self.assertEqual(self.call('GET','/tasks')[0]['move_fingerprint'],row['move_fingerprint'])

    def test_midnight_is_rejected_and_last_minute_is_supported(self):
        row=self.create(estimated_minutes=59)
        result=self.moved(row,self.move_body(row,start_time='23:00'))
        self.assertEqual(result['end_time'],'23:59')
        self.moved(result,self.move_body(result,start_time='23:15'),422)
        long=self.create(title='未定时长任务',estimated_minutes=1440)
        self.moved(long,self.move_body(long,start_time='00:00'),422)
        self.assertEqual(next(t for t in self.call('GET','/tasks') if t['id']==long['id'])['start_time'],None)

    def test_budget_requires_explicit_ack_and_ack_cannot_override_overlap(self):
        target=(date.today()+timedelta(days=1)).isoformat()
        self.create(exam_id=3,plan_date=target,estimated_minutes=100,start_time=None)
        row=self.create(estimated_minutes=60)
        body={**self.move_body(row),'plan_date':target,'start_time':'09:00'}
        preview=self.moved(row,body,preview=True)
        self.assertTrue(preview['budget_exceeded']); self.assertEqual(preview['planned_minutes'],160)
        self.assertEqual(self.moved(row,body,409)['detail']['code'],'daily_budget_exceeded')
        result=self.moved(row,{**body,'allow_over_budget':True})
        other=self.create(exam_id=3,estimated_minutes=30)
        self.moved(other,{**self.move_body(other),'plan_date':target,'start_time':'09:30','allow_over_budget':True},409)
        self.assertEqual(result['estimated_minutes'],60)

    def test_preview_race_rechecks_destination_before_mutation(self):
        row=self.create(repeat_rule='daily',repeat_until=(date.today()+timedelta(days=1)).isoformat())
        body=self.move_body(row,start_time='09:00')
        self.assertTrue(self.moved(row,body,preview=True)['can_save'])
        self.create(exam_id=3,start_time='09:30',end_time='10:00')
        self.moved(row,{**body,'allow_over_budget':True},409)
        original=next(t for t in self.call('GET','/tasks') if t['id']==row['id'])
        self.assertIsNone(original['start_time']); self.assertEqual(original['repeat_group_id'],row['repeat_group_id'])

    def test_snapshot_includes_identity_and_completion(self):
        row=self.create()
        with Session(self.engine) as db:
            task=db.get(Task,row['id']); task.created_at=task.created_at+timedelta(microseconds=1); db.commit()
        self.moved(row,self.move_body(row,start_time='09:00'),409)
        fresh=self.call('GET','/tasks')[0]
        self.call('POST',f"/tasks/{row['id']}/checkin")
        self.moved(fresh,self.move_body(fresh,start_time='09:00'),409)

    def test_concurrent_cross_course_moves_only_commit_one_overlap(self):
        rows=[self.create(estimated_minutes=30),self.create(exam_id=3,estimated_minutes=30)]
        barrier=Barrier(2)
        def move(row):
            barrier.wait(timeout=5)
            return self.client.post(f"/api/tasks/{row['id']}/move",json=self.move_body(row,start_time='09:00')).status_code
        with ThreadPoolExecutor(max_workers=2) as executor: statuses=list(executor.map(move,rows))
        self.assertEqual(sorted(statuses),[200,409]); self.assertEqual(sum(t['start_time'] is not None for t in self.call('GET','/tasks')),1)

    def test_failed_commit_rolls_back_date_time_and_repeat_detachment(self):
        row=self.create(repeat_rule='daily',repeat_until=(date.today()+timedelta(days=1)).isoformat())
        body={**self.move_body(row),'plan_date':(date.today()+timedelta(days=2)).isoformat(),'start_time':'09:00'}
        with patch('sqlalchemy.orm.Session.commit',side_effect=RuntimeError('simulated write failure')):
            self.moved(row,body,500)
        read=next(t for t in self.call('GET','/tasks') if t['id']==row['id'])
        self.assertEqual(read['move_fingerprint'],row['move_fingerprint']); self.assertEqual(read['repeat_group_id'],row['repeat_group_id'])


if __name__=='__main__': unittest.main()
