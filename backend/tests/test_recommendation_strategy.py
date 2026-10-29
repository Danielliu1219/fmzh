"""内容侧重、分钟守恒及真实模型分支的数据库/任务集成。"""
import json
import unittest
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, get_db
from app.models.models import Analysis, Exam, Material, StudySetting, Task, User, UserProfile
from app.routers import ai, features
from app.schemas.schemas import AnalysisResult, KnowledgePoint, PlanItem
from app.services.recommendation_strategy import apply_strategy, refresh_strategy, split_minutes, strategy_for
from app.services.score_targets import SCORE_BANDS, band_strategy
from app.utils.security import get_current_user


def profile(band='B+', **changes):
    return SimpleNamespace(target_band=band, target=band_strategy(band), learning_status=changes.pop('learning_status', 'medium'),
                           available_days=changes.pop('available_days', 7), daily_hours=changes.pop('daily_hours', 2), weak_chapters=changes.pop('weak_chapters', []), **changes)


def analysis():
    return AnalysisResult(course='数学', summary='仅参考资料',
        knowledge_points=[KnowledgePoint(name='极限', weight=.8), KnowledgePoint(name='积分', weight=.8), KnowledgePoint(name='级数', weight=.2)],
        review_plan=[PlanItem(day=1, date='2000-01-01', title='极限', estimated_minutes=120), PlanItem(day=2, date='2000-01-01', title='积分', estimated_minutes=120)])


class RecommendationStrategyTests(unittest.TestCase):
    def test_all_ten_targets_have_distinct_depth_without_adding_work(self):
        ratios = []
        for band in SCORE_BANDS:
            result = analysis()
            apply_strategy(result, profile(band))
            ratios.append(tuple(p.percent for p in result.strategy.phases))
            self.assertEqual(sum(p.percent for p in result.strategy.phases), 100)
            self.assertEqual(result.strategy.planned_minutes, 240)
            self.assertEqual(sum(k.suggest_minutes for k in result.knowledge_points), 240)
            self.assertEqual(sum(p.minutes for p in result.strategy.phases), 240)
            self.assertEqual(result.strategy.target_band, band)
        self.assertEqual(len(set(ratios)), 10)
        self.assertEqual([r[0] for r in ratios], sorted((r[0] for r in ratios), reverse=True))
        self.assertEqual([r[2] for r in ratios], sorted(r[2] for r in ratios))

    def test_weak_foundation_and_near_deadline_take_priority_over_high_target(self):
        weak, good = strategy_for(profile('A', learning_status='weak')), strategy_for(profile('A', learning_status='good'))
        self.assertGreater(weak.phases[0].percent, good.phases[0].percent)
        self.assertLess(weak.phases[2].percent, good.phases[2].percent)
        imminent = strategy_for(profile('A', learning_status='good', available_days=2))
        self.assertLessEqual(imminent.phases[2].percent, 10)
        self.assertEqual(sum(p.percent for p in imminent.phases), 100)

    def test_weak_chapter_changes_time_not_source_weight_or_statistics(self):
        result = analysis()
        original_weights = [k.weight for k in result.knowledge_points]
        apply_strategy(result, profile(weak_chapters='["积分"]'))
        self.assertGreater(result.knowledge_points[1].suggest_minutes, result.knowledge_points[0].suggest_minutes)
        self.assertIn('薄弱', result.knowledge_points[1].practice_hint)
        self.assertEqual([k.weight for k in result.knowledge_points], original_weights)

    def test_cumulative_daily_limit_and_extra_days_are_reported(self):
        result = analysis()
        result.review_plan += [PlanItem(day=1, date='2099-01-01', title='重复日', estimated_minutes=90), PlanItem(day=9, date='2099-01-01', title='超出天数', estimated_minutes=40)]
        apply_strategy(result, profile(daily_hours=.5, available_days=2), date(2026, 10, 29))
        self.assertEqual([p.estimated_minutes for p in result.review_plan], [30, 30])
        self.assertEqual([p.date for p in result.review_plan], ['2026-10-29', '2026-10-30'])
        self.assertEqual(result.strategy.deferred_minutes, 310)
        self.assertIn('310', result.strategy.notes[-1])
        for item in result.review_plan:
            self.assertEqual(sum(a.minutes for a in item.activities), item.estimated_minutes)

    def test_tiny_and_zero_budgets_never_force_minimum_hours(self):
        for minutes in (0, 1, 2, 17):
            result = analysis()
            result.knowledge_points = [KnowledgePoint(name=f'知识点{i}', weight=.7) for i in range(40)]
            apply_strategy(result, profile(daily_hours=minutes / 60, available_days=1))
            self.assertEqual(sum(k.suggest_minutes for k in result.knowledge_points), minutes)
            self.assertEqual(sum(p.minutes for p in result.strategy.phases), minutes)
            self.assertEqual(result.strategy.planned_minutes, minutes)

    def test_no_plan_or_no_points_and_legacy_target_remain_readable(self):
        legacy = SimpleNamespace(target='high', learning_status='good', available_days=4, daily_hours=1)
        result = AnalysisResult()
        apply_strategy(result, legacy)
        self.assertIsNone(result.strategy.target_band)
        self.assertEqual(result.strategy.planned_minutes, 0)
        self.assertIsNone(AnalysisResult.model_validate({'course': '历史分析'}).strategy)
        self.assertEqual(split_minutes(2, [0, 0, 0]), [1, 1, 0])
        self.assertEqual(split_minutes(5, []), [])

    def test_replan_refresh_does_not_retain_old_minute_totals(self):
        result = analysis()
        apply_strategy(result, profile())
        result.review_plan = [PlanItem(day=1, date=date.today().isoformat(), title='错题', estimated_minutes=23)]
        refresh_strategy(result)
        self.assertEqual(result.strategy.planned_minutes, 23)
        self.assertEqual(sum(p.minutes for p in result.strategy.phases), 23)
        self.assertEqual(sum(p.suggest_minutes for p in result.knowledge_points), 23)

    def test_strategy_never_rewrites_exam_statistics_or_citations(self):
        result = analysis()
        data = result.model_dump()
        data['question_types'] = [dict(type='计算题', count=4, frequency=.4, basis='仅课堂题统计', source='平时作业', citations=[dict(material_id=7, quote='原始引文')])]
        data['exam_focus'] = [dict(content='积分', frequency=3, basis='资料统计', source='课堂笔记')]
        result = AnalysisResult.model_validate(data)
        before = [result.question_types[0].model_dump(), result.exam_focus[0].model_dump()]
        apply_strategy(result, profile('A'))
        self.assertEqual(before, [result.question_types[0].model_dump(), result.exam_focus[0].model_dump()])


class RecommendationApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.engine = create_engine('sqlite:///' + (Path(self.temp.name) / 'strategy.db').as_posix(), connect_args={'check_same_thread': False})
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as db:
            db.add_all([User(id=1, username='owner', hashed_password='test-only'), User(id=2, username='other', hashed_password='test-only')])
            db.add_all([Exam(id=1, user_id=1, subject='数学', exam_date=date.today()+timedelta(days=5)), Exam(id=2, user_id=1, subject='英语', exam_date=date.today()+timedelta(days=10)), Exam(id=3, user_id=2, subject='私有课程', exam_date=date.today()+timedelta(days=3))])
            db.add(StudySetting(user_id=1, daily_minutes=120))
            db.add(UserProfile(user_id=1, exam_id=1, target='medium', target_band='B+', learning_status='weak', available_days=30, daily_hours=2, weak_chapters='["积分"]', is_complete=True))
            db.add(Material(user_id=1, exam_id=1, title='课堂资料', source_type='课堂笔记', file_path='test-only.txt', file_type='txt', text_content='极限与积分的基础概念和典型计算题。', parse_status='done'))
            db.add_all([Task(user_id=1, exam_id=2, title='其他科目', plan_date=date.today(), estimated_minutes=20, source='manual'), Task(user_id=2, exam_id=3, title='他人任务', plan_date=date.today(), estimated_minutes=60, source='ai')])
            db.commit()
            self.auth_key = db.get(User, 1).auth_key
        app = FastAPI()
        def database():
            with Session(self.engine) as db:
                yield db
        app.dependency_overrides[get_db] = database
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1, auth_key=self.auth_key)
        app.include_router(ai.router, prefix='/api/ai')
        app.include_router(features.router, prefix='/api/features')
        self.client = TestClient(app)
        self.real_mode = patch.object(settings, 'LLM_MOCK', False)
        self.real_mode.start()

    def tearDown(self):
        self.real_mode.stop()
        self.client.close()
        self.engine.dispose()
        self.temp.cleanup()

    def model_result(self):
        result = analysis().model_dump()
        result['review_plan'] = [dict(day=1, date='2000-01-01', title='极限', estimated_minutes=500), dict(day=1, date='2000-01-01', title='重复日', estimated_minutes=500), dict(day=2, date='2000-01-01', title='积分', estimated_minutes=500)]
        return result

    def test_real_model_path_is_constrained_saved_read_back_and_generates_real_tasks(self):
        with patch.object(ai, 'chat_json', return_value=self.model_result()) as llm, patch.object(ai.prompts, 'mock_generate_analysis') as mock:
            response = self.client.post('/api/ai/analyze', json={'exam_id': 1})
        self.assertEqual(response.status_code, 200, response.text)
        mock.assert_not_called()
        self.assertIn('基础巩固', llm.call_args.args[1])
        self.assertIn('80 分钟', llm.call_args.args[1])
        output = response.json()
        strategy = output['result']['strategy']
        self.assertEqual(strategy['daily_minutes'], 80)
        self.assertEqual(strategy['available_days'], 5)
        self.assertEqual(strategy['planned_minutes'], 160)
        self.assertEqual(strategy['deferred_minutes'], 1340)
        self.assertTrue(output['scheduling']['applied'])
        self.assertEqual(self.client.get('/api/ai/analyses/1').json()['result'], output['result'])
        review = self.client.get('/api/features/review', params={'exam_id': 1})
        self.assertEqual(review.status_code, 200, review.text)
        self.assertEqual(sum(k['suggest_minutes'] for k in review.json()['items']), 160)
        with Session(self.engine) as db:
            saved = db.get(Analysis, output['id'])
            self.assertEqual(json.loads(saved.result_json)['strategy'], strategy)
            self.assertEqual(json.loads(saved.result_json)['review_plan'][0]['activities'], output['result']['review_plan'][0]['activities'])
            work = db.query(Task).filter(Task.user_id == 1, Task.source == 'ai').all()
            self.assertEqual(sum(t.estimated_minutes for t in work), 160)
            load = defaultdict(int)
            for task in db.query(Task).filter(Task.user_id == 1).all():
                load[task.plan_date] += task.estimated_minutes
            self.assertTrue(all(minutes <= 120 for minutes in load.values()))
            self.assertTrue(all(t.plan_date < date.today()+timedelta(days=5) for t in work))
            self.assertEqual(db.query(Task).filter(Task.user_id == 2).one().title, '他人任务')

    def test_mock_backend_uses_same_policy_and_old_analysis_stays_compatible(self):
        with patch.object(settings, 'LLM_MOCK', True):
            response = self.client.post('/api/ai/analyze', json={'exam_id': 1})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNotNone(response.json()['result']['strategy'])
        with Session(self.engine) as db:
            row = db.query(Analysis).one()
            old = json.loads(row.result_json)
            old.pop('strategy')
            row.result_json = json.dumps(old)
            db.commit()
        self.assertIsNone(self.client.get('/api/ai/analyses/1').json()['result']['strategy'])

    def test_replan_with_dated_source_citations_saves_strategy_and_preserves_quotes(self):
        with patch.object(ai, 'chat_json', return_value=self.model_result()):
            generated = self.client.post('/api/ai/analyze', json={'exam_id': 1}).json()
        citations = generated['result']['knowledge_points'][0]['citations']
        self.assertTrue(citations)
        self.assertTrue(citations[0]['material_created_at'])
        preview = self.client.post('/api/ai/analyses/1/replan', json={'apply': False})
        self.assertEqual(preview.status_code, 200, preview.text)
        applied = self.client.post('/api/ai/analyses/1/replan', json={'apply': True, 'fingerprint': preview.json()['fingerprint']})
        self.assertEqual(applied.status_code, 200, applied.text)
        latest = self.client.get('/api/ai/analyses/1').json()['result']
        self.assertEqual(latest['knowledge_points'][0]['citations'], citations)
        self.assertEqual(latest['strategy']['planned_minutes'], sum(p['estimated_minutes'] for p in latest['review_plan']))
        self.assertEqual(sum(k['suggest_minutes'] for k in latest['knowledge_points']), latest['strategy']['planned_minutes'])

    def test_other_user_and_past_exam_do_not_call_model_or_write_analysis(self):
        with Session(self.engine) as db:
            db.get(Exam, 1).exam_date = date.today()-timedelta(days=1)
            db.commit()
        with patch.object(ai, 'chat_json') as llm:
            self.assertEqual(self.client.post('/api/ai/analyze', json={'exam_id': 3}).status_code, 404)
            self.assertEqual(self.client.post('/api/ai/analyze', json={'exam_id': 1}).status_code, 409)
            llm.assert_not_called()
        with Session(self.engine) as db:
            self.assertEqual(db.query(Analysis).count(), 0)

    def test_model_failure_does_not_overwrite_existing_tasks(self):
        with patch.object(ai, 'chat_json', return_value={'knowledge_points': [{'name': 'bad', 'weight': 999}]}) as llm:
            response = self.client.post('/api/ai/analyze', json={'exam_id': 1})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(llm.call_count, 2)
        with Session(self.engine) as db:
            self.assertEqual(db.query(Analysis).count(), 0)
            self.assertEqual(db.query(Task).filter(Task.user_id == 1).count(), 1)


if __name__ == '__main__':
    unittest.main()
