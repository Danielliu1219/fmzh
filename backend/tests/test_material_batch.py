"""隔离资料批量设置测试，不使用用户数据或真实模型。"""
import unittest
from datetime import date, timedelta
from unittest.mock import patch
from sqlalchemy.orm import Session
from app.models.models import Material, UserProfile
from app.routers import ai
import test_audit_fixes as fixtures


class MaterialBatchTests(unittest.TestCase):
    setUp = fixtures.AuditFixTests.setUp
    tearDown = fixtures.AuditFixTests.tearDown
    register = fixtures.AuditFixTests.register
    call = fixtures.AuditFixTests.call
    upload = fixtures.AuditFixTests.upload

    def test_upload_accepts_explicit_shared_weight_and_rejects_invalid_weight(self):
        response = self.client.post('/api/materials', headers=self.headers,
            files={'file': ('past-paper.txt', b'Independent test content')},
            data={'title': '试卷', 'source_type': '历年题', 'weight': '0.91'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['weight'], .91)
        response = self.client.post('/api/materials', headers=self.headers,
            files={'file': ('past-paper.txt', b'Independent test content')},
            data={'title': '不应保存', 'weight': '1.5'})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(len(self.call('GET', '/materials')), 1)

    def test_batch_deduplicates_ids_and_can_set_zero_weight(self):
        first, second = self.upload(), self.upload()
        rows = self.call('POST', '/materials/batch-update',
            {'material_ids': [second['id'], first['id'], second['id']], 'weight': 0})
        self.assertEqual([row['id'] for row in rows], [second['id'], first['id']])
        self.assertTrue(all(row['weight'] == 0 for row in rows))

    def test_mixed_account_or_missing_id_does_not_change_any_material(self):
        own = self.upload()
        other = self.register('second_owner')
        response = self.client.post('/api/materials',
            headers={'Authorization': 'Bearer ' + other['access_token']},
            files={'file': ('second.txt', b'Other account content')}, data={'title': '其他账号'})
        self.assertEqual(response.status_code, 200, response.text)
        foreign_id = response.json()['id']
        for invalid_id in (foreign_id, 999999):
            self.call('POST', '/materials/batch-update',
                {'material_ids': [own['id'], invalid_id], 'weight': 1}, status=404)
            self.assertEqual(self.call('GET', f"/materials/{own['id']}")['weight'], own['weight'])

    def test_source_default_or_explicit_override_preserves_document(self):
        item = self.upload()
        rows = self.call('POST', '/materials/batch-update',
            {'material_ids': [item['id']], 'source_type': '老师重点'})
        self.assertEqual(rows[0]['weight'], 1)
        rows = self.call('POST', '/materials/batch-update',
            {'material_ids': [item['id']], 'source_type': '历年题', 'weight': .93})
        self.assertEqual((rows[0]['source_type'], rows[0]['weight']), ('历年题', .93))
        with Session(self.engine) as db:
            document = db.get(Material, item['id'])
            self.assertIn('概念', document.text_content)
            self.assertTrue(document.file_path)

    def test_validation_and_commit_failure_are_atomic(self):
        item = self.upload()
        for payload in ({'material_ids': []}, {'material_ids': [item['id']]},
                {'material_ids': [item['id']], 'weight': -1}):
            self.call('POST', '/materials/batch-update', payload, status=422)
        self.call('POST', '/materials/batch-update',
            {'material_ids': [item['id']], 'source_type': 'unknown', 'weight': 1}, status=400)
        with patch('sqlalchemy.orm.Session.commit', side_effect=RuntimeError('injected failure')):
            response = self.client.post('/api/materials/batch-update', headers=self.headers,
                json={'material_ids': [item['id']], 'weight': 1})
            self.assertEqual(response.status_code, 500)
        self.assertEqual(self.call('GET', f"/materials/{item['id']}")['weight'], item['weight'])

    def test_manual_profile_completion_does_not_call_any_model(self):
        exam = self.call('POST', '/exams', {'subject': '手动补全', 'exam_date': str(date.today() + timedelta(days=5))})
        with Session(self.engine) as db:
            db.add(UserProfile(user_id=self.owner['user']['id'], exam_id=exam['id'], raw_text='保留的原始描述',
                weak_chapters='["极限"]', output_need='["复习计划"]', is_complete=False))
            db.commit()
        with patch.object(ai, 'chat_json', side_effect=AssertionError('Manual completion must not call a model')) as model:
            result = self.call('POST', '/ai/profile/complete', {'exam_id': exam['id'], 'target_band': 'B+',
                'learning_status': 'medium', 'available_days': 5, 'daily_hours': 1.5})
            self.assertEqual(model.call_count, 0)
        self.assertTrue(result['is_complete'])
        self.assertEqual(result['weak_chapters'], ['极限'])
        self.assertEqual(result['raw_text'], '保留的原始描述')
        self.assertEqual(result['daily_hours'], 1.5)
        self.call('POST', '/ai/profile/complete', {'exam_id': exam['id'], 'daily_hours': 0}, status=422)
        other = self.register('profile_other')
        self.call('POST', '/ai/profile/complete', {'exam_id': exam['id'], 'available_days': 2},
            headers={'Authorization': 'Bearer ' + other['access_token']}, status=404)
