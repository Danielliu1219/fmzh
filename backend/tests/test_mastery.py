import json
import unittest
from datetime import date, datetime, timedelta

from fastapi import Depends, FastAPI, Header
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.models import Analysis, Exam, QuizAttempt, User, UserProfile
from app.routers import ai
from app.services.mastery import knowledge_mastery
from app.utils.security import get_current_user


class MasteryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.owner = User(username='owner', hashed_password='unused')
        self.peer = User(username='peer', hashed_password='unused')
        self.db.add_all([self.owner, self.peer]); self.db.flush()
        self.exam = Exam(user_id=self.owner.id, subject='数学', exam_date=date.today()+timedelta(days=5))
        self.other = Exam(user_id=self.owner.id, subject='英语', exam_date=date.today()+timedelta(days=5))
        self.db.add_all([self.exam, self.other]); self.db.flush()
        profile = UserProfile(user_id=self.owner.id, exam_id=self.exam.id)
        self.db.add(profile); self.db.flush()
        data = dict(course='数学', summary='复习', knowledge_points=[dict(name=name, weight=0.8) for name in ['积分', '极限', '级数']])
        self.analysis = Analysis(user_id=self.owner.id, exam_id=self.exam.id, profile_id=profile.id, result_json=json.dumps(data))
        self.db.add(self.analysis); self.db.commit()
        app = FastAPI()
        def database():
            with Session(self.engine) as db: yield db
        def current(x_user_id: int = Header(default=self.owner.id), db=Depends(get_db)):
            return db.get(User, x_user_id)
        app.dependency_overrides[get_db] = database
        app.dependency_overrides[get_current_user] = current
        app.include_router(ai.router, prefix='/api/ai')
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close(); self.db.close(); self.engine.dispose()

    def attempt(self, items, minutes=0, status='submitted', user=None, exam=None):
        when = datetime.now()+timedelta(minutes=minutes)
        attempt = QuizAttempt(user_id=(user or self.owner).id, exam_id=(exam or self.exam).id,
                              analysis_id=self.analysis.id, subject='数学', questions_json='[]', status=status,
                              result_json=json.dumps(dict(items=items)), submitted_at=when if status == 'submitted' else None)
        self.db.add(attempt); self.db.commit()
        return attempt

    def point(self, name, correct, question='题目', unanswered=False):
        return dict(knowledge_point=name, correct=correct, question=question, unanswered=unanswered, answer='secret')

    def states(self):
        return knowledge_mastery(self.db, self.owner.id, self.exam.id, ['积分', '极限', '级数'])

    def test_empty_and_draft_remain_untested(self):
        self.attempt([self.point('积分', True)], status='active')
        self.assertTrue(all(point['status'] == 'untested' and point['score'] is None for point in self.states()))

    def test_latest_per_point_preserves_older_other_point_evidence(self):
        self.attempt([self.point('积分', False), self.point('极限', False, unanswered=True)])
        latest = self.attempt([self.point('积分', True)], minutes=1)
        points = self.states()
        self.assertEqual(points[0]['status'], 'mastered'); self.assertEqual(points[0]['attempt_id'], latest.id)
        self.assertEqual(points[1]['status'], 'weak'); self.assertTrue(points[1]['evidence'][0]['unanswered'])
        self.assertEqual(points[2]['status'], 'untested')

    def test_threshold_dedup_and_normalized_name(self):
        items = [self.point(' 积分 ', value, str(i)) for i, value in enumerate([True, True, True, True, False])]
        self.attempt([*items, items[0]])
        point = self.states()[0]
        self.assertEqual((point['total'], point['score'], point['status']), (5, 80.0, 'mastered'))

    def test_no_cross_user_or_subject_evidence(self):
        self.attempt([self.point('积分', True)], user=self.peer)
        self.attempt([self.point('积分', True)], exam=self.other)
        self.assertEqual(self.states()[0]['status'], 'untested')
        response = self.client.get(f'/api/ai/analyses/{self.exam.id}/mastery', headers={'X-User-ID': str(self.peer.id)})
        self.assertEqual(response.status_code, 404)

    def test_http_schema_and_evidence_excludes_answers(self):
        self.attempt([self.point('积分', True)])
        response = self.client.get(f'/api/ai/analyses/{self.exam.id}/mastery')
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data['points'][0]['status'], 'mastered')
        self.assertNotIn('secret', response.text)
        self.assertIn('80%', data['note'])

    def test_corrupt_evidence_is_ignored_without_marking_mastered(self):
        self.attempt([{}, 'invalid', dict(knowledge_point='积分', correct='yes', question='bad')])
        self.assertEqual(self.states()[0]['status'], 'untested')


if __name__ == '__main__': unittest.main()
