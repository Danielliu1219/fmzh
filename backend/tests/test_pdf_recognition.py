"""公式识别缓存、题号范围、原始资料保留与解题输入的隔离回归。"""
import json
import os
import unittest
from unittest.mock import patch
from unittest.mock import Mock
from PIL import Image
from tempfile import TemporaryDirectory
from pathlib import Path

from pypdf import PdfWriter
from sqlalchemy.orm import Session

from app.models.models import Material, QaConversation, QaMessage
from app.routers import study_sources
from app.schemas.schemas import AnalysisResult, KnowledgePoint
from app.services import pdf_recognition
from app.services.file_parser import parse_document
from app.services.study_sources import display_analysis, material_units, keyword_match
import test_source_evidence as fixtures


FIRST = '二、解答题（每小题8分，共48分）\n1. 求极限。\n2. 求参数。\n3. 求不定积分 $\\int \\frac{2}{(x+1)(x^2+1)}dx$。'
SECOND = '4. 求函数表达式。\n5. 判断无穷小阶数。'


class PdfRecognitionTests(unittest.TestCase):
    tearDown = fixtures.EvidenceTests.tearDown
    material = fixtures.EvidenceTests.material

    def setUp(self):
        fixtures.EvidenceTests.setUp(self)
        self.client.app.include_router(study_sources.router, prefix='/api/study-sources')
        patcher = patch.object(pdf_recognition, 'UPLOAD_DIR', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        path = self.root / 'formula.pdf'
        writer = PdfWriter()
        writer.add_blank_page(width=595, height=842)
        writer.add_blank_page(width=595, height=842)
        writer.write(path)
        text = '二、解答题\n3. 公式碎片及混杂文字\n第二页别的题混在这里'
        self.source = self.material(text, locations=[dict(start=0, end=24, kind='page', number=1, label='第 1 页'),
            dict(start=24, end=len(text), kind='page', number=2, label='第 2 页')])
        self.source.file_type = 'pdf'
        self.source.source_type = '历年题'
        self.source.file_path = str(path)
        self.db.commit()
        self.unit = material_units(self.source)[0]

    def recognize(self):
        response = self.client.get(f'/api/study-sources/{self.source.id}/unit', params={'unit_id': self.unit['id'], 'recognize': True})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_recognition_preserves_original_ids_and_text_and_reuses_page_cache(self):
        original = self.source.text_content
        with patch.object(pdf_recognition, 'recognize_pdf_pages', return_value={'1': FIRST, '2': SECOND}) as worker:
            first = self.recognize()
            second = self.recognize()
        self.assertEqual(worker.call_count, 1)
        self.assertEqual(first, second)
        self.assertEqual(first['id'], self.unit['id'])
        self.assertEqual(first['pages'], [1])
        self.assertIn('\\frac{2}{(x+1)(x^2+1)}', first['question_text'])
        self.assertNotIn('4. 求函数', first['question_text'])
        self.db.refresh(self.source)
        self.assertEqual(self.source.text_content, original)

    def test_other_users_cannot_trigger_ocr_for_private_source(self):
        with patch.object(pdf_recognition, 'recognize_pdf_pages') as worker:
            response = self.client.get(f'/api/study-sources/{self.source.id}/unit',
                params={'unit_id': self.unit['id'], 'recognize': True}, headers={'x-user-id': str(self.peer.id)})
        self.assertEqual(response.status_code, 404)
        worker.assert_not_called()

    def test_native_question_anchors_restore_missing_numbers_and_keep_formula_with_its_question(self):
        def block(text, y, kind='text', x=20):
            return dict(text=text, type=kind, position=[[x, y], [190, y], [190, y+12], [x, y+12]], line_number=y)
        anchors = [dict(number='3', kind='question', box=(10, 30, 18, 42)),
                   dict(number='4', kind='question', box=(10, 100, 18, 112))]
        blocks = [block('3.求不定积分', 30), block('\\int \\frac{2}{(x+1)(x^2+1)}dx', 28, 'embedding', x=80),
                  block('.若连续函数满足条件', 100)]
        with Image.new('RGB', (200, 180), 'white') as picture:
            text = pdf_recognition.ordered_page_text(blocks, anchors, [], picture, Mock())
        self.assertTrue(text.startswith('3.'))
        self.assertIn('4. 若连续函数', text)
        self.assertLess(text.index('\\int'), text.index('4.'))

    def test_integral_is_recognized_again_only_when_original_pdf_contains_integral_glyph(self):
        block = dict(text='\\langle \\frac{2}{x+1}dx\\rangle', type='embedding',
            position=[[20, 20], [110, 20], [110, 50], [20, 50]])
        spans = [dict(text='\uf0f2', font='SymbolMT', box=(22, 21, 28, 49)),
                 dict(text='2', font='Times', box=(55, 23, 65, 35))]
        engine = Mock()
        engine.latex_ocr.recognize.return_value = dict(text='\\int \\frac{2}{x+1}dx')
        with Image.new('RGB', (200, 100), 'white') as picture:
            fixed = pdf_recognition.repair_integral(block, spans, picture, engine)
        self.assertIn('\\int', fixed['text'])
        engine.latex_ocr.recognize.assert_called_once()

    def test_continued_question_before_new_section_is_preserved(self):
        blocks = [dict(text='若连续函数满足条件', type='text',
                       position=[[20, 20], [190, 20], [190, 40], [20, 40]], line_number=0),
                  dict(text='三、应用题', type='text',
                       position=[[20, 100], [190, 100], [190, 120], [20, 120]], line_number=1)]
        anchors = [dict(number='4', kind='question', box=(10, 20, 18, 40))]
        with Image.new('RGB', (200, 180), 'white') as picture:
            text = pdf_recognition.ordered_page_text(blocks, anchors, [], picture, Mock())
        self.assertTrue(text.startswith('4. 若连续函数'))
        self.assertLess(text.index('4.'), text.index('三、应用题'))

    def test_readable_native_chinese_corrects_ocr_within_the_same_box(self):
        block = dict(text='球不定积分', type='text', position=[[20, 20], [110, 20], [110, 40], [20, 40]])
        spans = [dict(text='求不定积分', box=(20, 20, 110, 40))]
        self.assertEqual(pdf_recognition.restore_native_chinese(block, spans)['text'], '求不定积分')
        self.assertEqual(pdf_recognition.restore_native_chinese(block, [])['text'], '球不定积分')

    def test_material_change_during_recognition_rejects_cache_write(self):
        def change(*args):
            with Session(self.engine) as db:
                source = db.get(Material, self.source.id)
                source.text_content += '修订'
                db.commit()
            return {'1': FIRST, '2': SECOND}
        with patch.object(pdf_recognition, 'recognize_pdf_pages', side_effect=change):
            response = self.client.get(f'/api/study-sources/{self.source.id}/unit', params={'unit_id': self.unit['id'], 'recognize': True})
        self.assertEqual(response.status_code, 409, response.text)
        self.db.refresh(self.source)
        self.assertEqual(json.loads(self.source.pdf_ocr_json), {})

    def test_pdf_parser_uses_formula_ocr_for_scanned_pages_and_keeps_page_locations(self):
        with patch.object(pdf_recognition, 'recognize_pdf_pages', side_effect=lambda path, pages: {str(p): FIRST if p == 1 else SECOND for p in pages}):
            text, locations = parse_document(self.source.file_path, 'pdf')
        self.assertIn('\\frac{2}', text)
        self.assertEqual([part['number'] for part in locations], [1, 2])

    def test_knowledge_frequencies_reuse_weights_and_deduplicate_source_units(self):
        self.source.pdf_ocr_json = json.dumps({'engine': pdf_recognition.ENGINE_VERSION, 'pages': {'1': FIRST, '2': SECOND}})
        result = AnalysisResult(course='数学', knowledge_points=[KnowledgePoint(name='不定积分', weight=.48,
            source_ids=[self.unit['id'], self.unit['id']]), KnowledgePoint(name='不存在的知识点', weight=.2)])
        output = display_analysis(result, [self.source])
        self.assertEqual(output.knowledge_points[0].weight, .48)
        self.assertEqual(output.knowledge_points[0].occurrence_count, 1)
        self.assertEqual(output.knowledge_points[0].occurrence_material_count, 1)
        self.assertIsNone(output.knowledge_points[1].occurrence_count)

    def test_definite_integral_does_not_match_indefinite_integral_text(self):
        self.assertFalse(keyword_match('定积分应用', '求不定积分。'))
        self.assertTrue(keyword_match('不定积分', '求不定积分。'))
        self.assertTrue(keyword_match('定积分应用', '用定积分计算旋转体体积。'))

    def test_new_formula_input_generates_new_answer_and_keeps_paid_history(self):
        with patch.object(pdf_recognition, 'recognize_pdf_pages', return_value={'1': FIRST, '2': SECOND}):
            detail = self.recognize()
        conversation = QaConversation(user_id=self.owner.id, exam_id=self.exam.id)
        self.db.add(conversation)
        self.db.flush()
        old = QaMessage(conversation_id=conversation.id, role='assistant', content='旧文字层生成的答案',
            source_unit_id=self.unit['id'], source_help_kind='answer')
        self.db.add(old)
        self.db.commit()
        payload = dict(content='给出指定题目的参考解答', source_material_id=self.source.id, source_unit_id=self.unit['id'],
            source_help_kind='answer', source_input_hash=detail['input_hash'])
        with patch('app.routers.ai.settings.LLM_MOCK', False), patch('app.routers.ai.chat_text', return_value='新版公式解答') as model:
            response = self.client.post(f'/api/ai/qa/conversations/{conversation.id}/messages', json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(model.call_count, 1)
        self.assertIn('\\frac{2}{(x+1)(x^2+1)}', model.call_args.args[0])
        self.assertNotIn('第二页别的题', model.call_args.args[0])
        history = self.client.get(f'/api/study-sources/{self.source.id}/ai-help', params={'unit_id': self.unit['id']}).json()['messages']
        self.assertEqual([item['current_input'] for item in history], [False, True])
        self.assertEqual(history[0]['content'], old.content)


class ModelPreparationTests(unittest.TestCase):
    def test_offline_check_reports_missing_weights_and_reuses_complete_files(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = {'version': '1.1', 'models': {'sample': {'revision': 'fixed-revision', 'files': {'weights.onnx': 4}}}}
            (root / 'ocr_models.json').write_text(json.dumps(manifest), encoding='utf-8')
            model = root / 'models' / '1.1' / 'sample-onnx' / 'weights.onnx'
            with patch.object(pdf_recognition, '__file__', str(root / 'pdf_recognition.py')), patch.dict(os.environ, {'PIX2TEXT_HOME': str(root / 'models')}), patch('huggingface_hub.snapshot_download') as download:
                with self.assertRaisesRegex(RuntimeError, '缺失或不完整'):
                    pdf_recognition.prepare_model_files(download=False)
                download.assert_not_called()
                model.parent.mkdir(parents=True)
                model.write_bytes(b'1234')
                self.assertEqual(pdf_recognition.prepare_model_files(download=False), root / 'models')
                download.assert_not_called()

    def test_incomplete_model_files_are_repaired_using_pinned_public_models(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = {'version': '1.1', 'models': {'sample': {'revision': 'fixed-revision', 'files': {'weights.onnx': 4}}}}
            (root / 'ocr_models.json').write_text(json.dumps(manifest), encoding='utf-8')
            model = root / 'models' / '1.1' / 'sample-onnx' / 'weights.onnx'
            model.parent.mkdir(parents=True)
            model.write_bytes(b'1')
            def repair(**kwargs):
                model.write_bytes(b'1234')
            with patch.object(pdf_recognition, '__file__', str(root / 'pdf_recognition.py')), patch.dict(os.environ, {'PIX2TEXT_HOME': str(root / 'models')}), patch('huggingface_hub.snapshot_download', side_effect=repair) as download:
                pdf_recognition.prepare_model_files()
                self.assertTrue(download.call_args.kwargs['force_download'])
                self.assertEqual(download.call_args.kwargs['revision'], 'fixed-revision')
                self.assertFalse(download.call_args.kwargs['token'])
                self.assertEqual(model.read_bytes(), b'1234')
