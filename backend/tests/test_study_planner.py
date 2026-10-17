import unittest
from datetime import date

from app.services.study_planner import distribute

TODAY = date(2026, 10, 17)
EXAMS = {1: {'exam_date': '2026-10-20'}, 2: {'exam_date': '2026-10-21'}, 3: {'exam_date': '2026-10-22'}}


def task(id, exam_id, minutes, **changes):
    return dict(id=id, exam_id=exam_id, estimated_minutes=minutes, title=f'task {id}', plan_date='2026-10-17', priority=2, source='ai', is_done=False, **changes)


class StudyPlannerTests(unittest.TestCase):
    def test_multiple_courses_share_capacity_and_preserve_work(self):
        plan = distribute([task(1, 1, 300), task(2, 2, 240), task(3, 3, 180)], EXAMS, 240, TODAY)
        self.assertFalse(plan['conflicts'])
        self.assertTrue(all(d['minutes'] <= 240 for d in plan['days']))
        self.assertEqual(sum(a['minutes'] for a in plan['assignments']), 720)
        self.assertGreater(len({a['exam_id'] for a in plan['assignments'] if a['date'] == '2026-10-17'}), 1)
        self.assertTrue(all(a['date'] < EXAMS[a['exam_id']]['exam_date'] for a in plan['assignments']))

    def test_oversized_task_is_split_not_overfilled(self):
        plan = distribute([task(1, 1, 360)], EXAMS, 120, TODAY)
        self.assertFalse(plan['conflicts'])
        self.assertEqual([a['minutes'] for a in plan['assignments']], [120, 120, 120])

    def test_infeasible_work_is_explicit_and_conserved(self):
        plan = distribute([task(1, 1, 800)], EXAMS, 120, TODAY)
        self.assertEqual(sum(a['minutes'] for a in plan['assignments']) + sum(c['minutes'] for c in plan['conflicts']), 800)
        self.assertTrue(plan['conflicts'])
        self.assertTrue(all(d['minutes'] <= 120 for d in plan['days']))

    def test_manual_and_completed_reserve_time_and_are_not_moved(self):
        manual = task(2, 2, 80); manual['source'] = 'manual'
        done = task(3, 2, 40); done['is_done'] = True
        plan = distribute([task(1, 1, 180), manual, done], EXAMS, 120, TODAY)
        self.assertFalse(plan['conflicts'])
        self.assertFalse(any(a['date'] == '2026-10-17' for a in plan['assignments']))
        self.assertEqual({a['task_id'] for a in plan['assignments']}, {1})

    def test_near_deadline_cannot_be_starved_by_larger_later_course(self):
        exams = {1: {'exam_date': '2026-10-18'}, 2: {'exam_date': '2026-10-22'}}
        plan = distribute([task(1, 1, 120), task(2, 2, 480)], exams, 120, TODAY)
        self.assertFalse(plan['conflicts'])
        self.assertEqual(sum(a['minutes'] for a in plan['assignments'] if a['task_id'] == 1 and a['date'] == '2026-10-17'), 120)

    def test_past_exam_and_fixed_overload_are_reported(self):
        exams = {1: {'exam_date': '2026-10-16'}}
        manual = task(2, 1, 200); manual['source'] = 'manual'
        plan = distribute([task(1, 1, 60), manual], exams, 120, TODAY)
        self.assertEqual(len(plan['conflicts']), 2)
        self.assertFalse(plan['assignments'])

    def test_empty_input(self):
        self.assertEqual(distribute([], EXAMS, 240, TODAY)['assignments'], [])


if __name__ == '__main__':
    unittest.main()
