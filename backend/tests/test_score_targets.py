"""目标区间保存、模型上下文和旧库兼容；全部使用临时数据库。"""
import unittest
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, get_db
from app.models.models import Exam, Material, User, UserProfile
from app.routers import ai
from app.services.schema_upgrade import upgrade_schema
from app.services.score_targets import SCORE_BANDS
from app.utils.security import get_current_user


class ScoreTargetTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.engine = create_engine('sqlite:///' + (Path(self.temp.name) / 'targets.db').as_posix(), connect_args={'check_same_thread': False})
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as db:
            db.add_all([User(id=1, username='owner', hashed_password='test-only'), User(id=2, username='other', hashed_password='test-only')])
            db.add_all([Exam(id=1, user_id=1, subject='高等数学', exam_date=date.today()+timedelta(days=5)), Exam(id=2, user_id=2, subject='大学英语', exam_date=date.today()+timedelta(days=7))])
            db.add(Material(user_id=1, exam_id=1, title='复习笔记', source_type='课堂笔记', file_path='test-only.txt', file_type='txt', text_content='极限与积分的基本概念和常见计算方法', parse_status='done'))
            db.commit()
        app = FastAPI()
        def database():
            with Session(self.engine) as db:
                yield db
        app.dependency_overrides[get_db] = database
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
        app.include_router(ai.router, prefix='/api/ai')
        self.client = TestClient(app)
        self.mock = patch.object(settings, 'LLM_MOCK', True)
        self.mock.start()

    def tearDown(self):
        self.mock.stop()
        self.client.close()
        self.engine.dispose()
        self.temp.cleanup()

    def create_profile(self, **changes):
        return self.client.post('/api/ai/profile', json={
            'exam_id': 1, 'raw_text': '我基础差，只想及格，还有5天考试，每天能学3小时，薄弱的是极限。',
            'target_band': 'A-', **changes,
        })

    def test_all_ten_bands_persist_and_override_conflicting_text(self):
        for band in SCORE_BANDS:
            with self.subTest(band=band):
                response = self.create_profile(target_band=band)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()['target_band'], band)
                saved = self.client.get('/api/ai/profile/1').json()
                self.assertEqual(saved['target_band'], band)
                self.assertTrue(saved['is_complete'])
        self.assertEqual(saved['target'], 'high')

    def test_band_reaches_analysis_and_user_notes_reach_model_context(self):
        self.assertEqual(self.create_profile().status_code, 200)
        with Session(self.engine) as db:
            context = ai._profile_to_text(db.query(UserProfile).one())
            self.assertIn('85–89 分', context)
            self.assertIn('3.7', context)
            self.assertIn('薄弱的是极限', context)
        analysis = self.client.post('/api/ai/analyze', json={'exam_id': 1})
        self.assertEqual(analysis.status_code, 200, analysis.text)
        self.assertIn('85–89 分', analysis.json()['result']['summary'])
        self.assertTrue(any('综合' in item['title'] for item in analysis.json()['result']['review_plan']))

    def test_supplement_preserves_band_and_legacy_new_description_clears_it(self):
        self.create_profile()
        supplement = self.client.post('/api/ai/profile', json={'exam_id': 1, 'supplement': '每天能学4小时'})
        self.assertEqual(supplement.json()['target_band'], 'A-')
        legacy = self.client.post('/api/ai/profile', json={'exam_id': 1, 'raw_text': '我基础差，只想及格，还有5天考试，每天能学3小时'})
        self.assertIsNone(legacy.json()['target_band'])
        self.assertEqual(legacy.json()['target'], 'pass')

    def test_invalid_band_and_other_users_profile_are_rejected(self):
        self.assertEqual(self.create_profile(target_band='95').status_code, 422)
        self.assertEqual(self.client.get('/api/ai/profile/2').status_code, 404)
        self.assertEqual(self.create_profile(exam_id=2).status_code, 404)
        self.assertEqual(self.client.get('/api/ai/profile/1').status_code, 404)

    def test_existing_profile_table_upgrade_is_additive_and_repeatable(self):
        with self.engine.begin() as conn:
            conn.execute(text('ALTER TABLE user_profiles DROP COLUMN target_band'))
            conn.execute(text("INSERT INTO user_profiles (user_id,exam_id,raw_text,target) VALUES (1,1,'原有画像','pass')"))
        upgrade_schema(self.engine)
        upgrade_schema(self.engine)
        with self.engine.connect() as conn:
            saved = conn.execute(text('SELECT raw_text,target,target_band FROM user_profiles')).one()
            self.assertEqual(tuple(saved), ('原有画像', 'pass', None))


if __name__ == '__main__':
    unittest.main()
