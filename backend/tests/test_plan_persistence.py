import unittest
from datetime import date, timedelta
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models.models import Exam, StudySetting, Task, User
from app.services.plan_service import create_tasks_from_plan


class PlanPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, autoflush=False)
        self.db.add(User(id=1, username='test', hashed_password='unused'))
        self.db.add(Exam(id=1, user_id=1, subject='Math', exam_date=date.today()+timedelta(days=5)))
        self.db.add(StudySetting(user_id=1, daily_minutes=120))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_regeneration_deducts_completed_split_and_preserves_record(self):
        completed=Task(user_id=1, exam_id=1, title='Integrals（分段 1/2）', estimated_minutes=60, plan_date=date.today(), is_done=True, source='ai')
        self.db.add(completed)
        self.db.commit()
        item=SimpleNamespace(title='Integrals', estimated_minutes=180, date=date.today().isoformat(), priority=1)
        result=create_tasks_from_plan(self.db,1,1,1,[item])
        self.assertTrue(result['applied'])
        self.assertTrue(self.db.get(Task,completed.id).is_done)
        rows=self.db.query(Task).all()
        self.assertEqual(sum(t.estimated_minutes for t in rows),180)
        self.assertEqual(sum(t.estimated_minutes for t in rows if not t.is_done),120)

    def test_infeasible_generation_rolls_back_task_replacement(self):
        prior=Task(user_id=1,exam_id=1,title='Existing plan',estimated_minutes=30,plan_date=date.today(),source='ai')
        self.db.add(prior)
        self.db.commit()
        item=SimpleNamespace(title='Impossible plan',estimated_minutes=10000,date=date.today().isoformat(),priority=1)
        result=create_tasks_from_plan(self.db,1,1,1,[item])
        self.assertFalse(result['applied'])
        self.assertEqual([(t.id,t.title,t.estimated_minutes) for t in self.db.query(Task).all()],[(prior.id,'Existing plan',30)])


if __name__ == '__main__':
    unittest.main()
