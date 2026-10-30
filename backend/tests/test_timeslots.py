"""7.5 独立区间、窗口、稀疏记录、账号边界及真实只读接口。"""
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.models.models import FocusSession, StudySetting, Task
from app.routers import focus
from app.services.timeslots import summarize
import test_task_details as fixtures

NOW = datetime(2026, 10, 30, 20)


def row(a, minutes=25, **changes):
    a = datetime.fromisoformat(a) if isinstance(a, str) else a
    return SimpleNamespace(start_time=a, end_time=a+timedelta(minutes=minutes), duration_minutes=minutes, **changes)


def history(now=NOW):
    return [row((now-timedelta(days=d)).replace(hour=h, minute=0, second=0, microsecond=0)) for d in (1,2,3) for h in (9,19)]


class IntervalTests(unittest.TestCase):
    def test_repeated_history_ranks_and_conserves_budget(self):
        result = summarize(history(), 240, NOW)
        self.assertEqual(result['mode'], 'history')
        self.assertEqual((result['session_count'],result['study_days'],result['history_minutes']), (6,3,150))
        self.assertEqual([s['start'] for s in result['slots']], ['08:00','18:00'])
        self.assertEqual(sum(s['minutes'] for s in result['slots']),240)
        self.assertTrue(all(s['study_days']==3 for s in result['slots']))

    def test_duplicate_and_overlap_are_not_added_twice(self):
        rows=history()
        rows += [rows[0],row(rows[0].start_time+timedelta(minutes=10))]
        result=summarize(rows,240,NOW)
        self.assertEqual(result['history_minutes'],160)
        self.assertEqual(result['ignored_sessions'],1)

    def test_thresholds_require_days_records_and_unique_minutes(self):
        for rows in ([],history()[:2],history()[:4], [row(NOW-timedelta(minutes=30+i)) for i in range(10)]):
            self.assertEqual(summarize(rows,240,NOW)['mode'],'insufficient')
        # 分散到从不重复的时段，即使总天数/分钟足够，也不声称有稳定习惯。
        rows=[row(NOW.replace(hour=i*2)-timedelta(days=i+1)) for i in range(5)]
        self.assertEqual(summarize(rows,240,NOW)['mode'],'insufficient')

    def test_cross_midnight_splits_calendar_days_and_two_hour_bins(self):
        result=summarize([row('2026-10-29T23:45:00',30)],30,NOW)
        self.assertEqual((result['study_days'],result['history_minutes']),(2,30))

    def test_window_clips_boundary_and_ignores_old_future_invalid_records(self):
        old=row('2026-10-02T23:45:00',30)
        invalid=row('2026-10-29T09:00:00'); invalid.duration_minutes=100
        reverse=row('2026-10-29T10:00:00'); reverse.end_time=reverse.start_time-timedelta(minutes=2)
        rows=[old, invalid, reverse, row('2026-10-30T19:50:00'),row('2026-10-01T09:00:00'),row('2026-11-01T09:00:00')]
        result=summarize(rows,240,NOW)
        self.assertEqual(result['window_start'],'2026-10-03')
        self.assertEqual(result['history_minutes'],15)
        self.assertEqual(result['ignored_sessions'],3)

    def test_aware_times_convert_to_beijing(self):
        rows=[row(f'2026-10-{d}T01:00:00+00:00') for d in (27,28,29)]
        rows += [row(f'2026-10-{d}T11:00:00+00:00') for d in (27,28,29)]
        self.assertEqual(summarize(rows,240,NOW)['slots'][0]['start'],'08:00')

    def test_small_and_large_budgets_never_overfill(self):
        for budget in (30,31,120,240,960):
            for rows in ([],history()):
                result=summarize(rows,budget,NOW)
                self.assertEqual(sum(s['minutes'] for s in result['slots'])+result['unallocated_minutes'],budget)
                self.assertTrue(all(0<s['minutes']<=120 for s in result['slots']))
        self.assertIn('未分配',summarize(history(),960,NOW)['note'])


class TimeslotApiTests(unittest.TestCase):
    tearDown=fixtures.TaskDetailsTests.tearDown
    call=fixtures.TaskDetailsTests.call
    def setUp(self):
        fixtures.TaskDetailsTests.setUp(self)
        self.client.app.include_router(focus.router,prefix='/api/focus')
        self.now=datetime.now().replace(second=0,microsecond=0)
        with Session(self.engine) as db:
            for r in history(self.now):
                db.add(FocusSession(user_id=1,exam_id=1,start_time=r.start_time,end_time=r.end_time,duration_minutes=r.duration_minutes))
            db.add(FocusSession(user_id=2,exam_id=2,start_time=self.now-timedelta(minutes=50),end_time=self.now-timedelta(minutes=25),duration_minutes=25))
            db.add(Task(user_id=1,exam_id=3,title='只打卡',plan_date=self.now.date(),is_done=True,done_at=self.now-timedelta(minutes=1),estimated_minutes=999))
            db.commit()

    def test_scope_ownership_and_checkin_are_separate(self):
        all_=self.call('GET','/features/timeslots')
        self.assertEqual((all_['mode'],all_['daily_minutes'],all_['session_count'],all_['checkin_count']),('history',120,6,1))
        english=self.call('GET','/features/timeslots?exam_id=3')
        self.assertEqual((english['mode'],english['session_count'],english['history_minutes'],english['checkin_count']),('insufficient',0,0,1))
        self.call('GET','/features/timeslots?exam_id=2',status=404)
        self.call('GET','/features/timeslots?exam_id=999',status=404)
        peer=self.call('GET','/features/timeslots',headers={'x-user':'2'})
        self.assertEqual(peer['session_count'],1)

    def test_readonly_and_current_shared_budget(self):
        with Session(self.engine) as db:
            before=[(t.id,t.plan_date,t.estimated_minutes) for t in db.query(Task)]
            db.get(StudySetting,1).daily_minutes=31; db.commit()
        result=self.call('GET','/features/timeslots?exam_id=1')
        self.assertEqual(result['recommended_minutes'],31)
        with Session(self.engine) as db:
            self.assertEqual(before,[(t.id,t.plan_date,t.estimated_minutes) for t in db.query(Task)])
            self.assertEqual(db.query(FocusSession).count(),7)

    def test_focus_save_normalizes_timezone_and_rejects_bad_intervals(self):
        output=self.call('POST','/focus/sessions',{'exam_id':1,'duration_minutes':25,'start_time':'2026-10-27T01:00:00Z','end_time':'2026-10-27T01:25:00Z'})
        self.assertEqual(output['start_time'],'2026-10-27T09:00:00')
        for a,b in [('2026-10-27T09:00:00','2026-10-27T08:00:00'),('2026-10-27T09:00:00','2026-10-27T11:00:00'),('2099-01-01T09:00:00','2099-01-01T09:25:00')]:
            self.call('POST','/focus/sessions',{'duration_minutes':25,'start_time':a,'end_time':b},status=422)
        self.call('POST','/focus/sessions',{'exam_id':2,'duration_minutes':25},status=404)
