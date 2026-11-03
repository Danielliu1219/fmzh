"""来源索引、原页、权限与任务保留回归；测试不访问付费平台。"""
import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from pypdf import PdfWriter

from app.models.models import Material, Task, AIJob
from app.routers import study_sources, collections, tasks, ai, jobs
from app.schemas.schemas import AnalysisResult, KnowledgePoint, PlanItem, SourceReference
from app.services.study_sources import material_units, build_context, library, attach_study_sources, unit_detail
from app.services.source_evidence import content_hash
from app.services import study_planner
from app.services.schema_upgrade import upgrade_schema
import test_source_evidence as evidence_fixtures


class StudySourcesTests(unittest.TestCase):
    setUp = evidence_fixtures.EvidenceTests.setUp
    tearDown = evidence_fixtures.EvidenceTests.tearDown
    material = evidence_fixtures.EvidenceTests.material
    analysis = evidence_fixtures.EvidenceTests.analysis

    def setup_routes(self):
        self.client.app.include_router(study_sources.router, prefix='/api/study-sources')
        self.client.app.include_router(collections.router, prefix='/api/collections')
        self.client.app.include_router(tasks.router, prefix='/api/tasks')

    def paper(self):
        text = '一、计算题\n1. 求极限。\n(1) 第一小问\n(2) 第二小问\n答案：42\n2. 计算定积分。\n跨页题干\n'
        row = self.material(text, locations=[dict(start=0,end=45,kind='page',number=1,label='第 1 页'),
                                            dict(start=45,end=len(text),kind='page',number=2,label='第 2 页')])
        row.file_type='pdf'; row.source_type='历年题'; self.db.commit()
        return row

    def test_composite_question_keeps_stem_subquestions_and_page_range(self):
        material=self.paper();units=material_units(material)
        self.assertEqual([u['question_number'] for u in units],['1','2'])
        self.assertEqual(units[0]['subquestions'],['1','2'])
        self.assertIn('一、计算题',units[0]['label'])
        self.assertIn('第 1 题',units[0]['label'])
        self.assertIn('第二小问',units[0]['text'])
        self.assertNotIn('2. 计算定积分',units[0]['text'])
        self.assertEqual(units[1]['pages'],[1,2])
        detail=unit_detail(units[0])
        self.assertEqual(detail['original_answer'],'答案：42')
        self.assertNotIn('答案',detail['question_text'])

    def test_ppt_slides_keep_true_slide_numbers_and_do_not_invent_questions(self):
        text='极限的定义\n导数的定义'
        material=self.material(text,locations=[dict(start=0,end=6,kind='slide',number=3,label='第 3 张幻灯片'),dict(start=7,end=len(text),kind='slide',number=4,label='第 4 张幻灯片')])
        material.file_type='pptx';self.db.commit()
        units=material_units(material)
        self.assertEqual(len(units),2)
        self.assertEqual(units[0]['location'],'第 3 张幻灯片')
        self.assertEqual(units[0]['kind'],'reading')
        self.assertEqual(units[0]['pages'],[])

    def test_no_number_or_location_falls_back_to_text_without_fabricated_page(self):
        material=self.material('极限定义和连续函数的概念。')
        material.source_type='历年题';self.db.commit()
        unit=material_units(material)[0]
        self.assertEqual(unit['kind'],'reading')
        self.assertEqual(unit['pages'],[])
        self.assertIn('旧资料未保存页码',unit['location'])

    def test_ids_survive_title_edits_but_not_text_or_lifecycle_replacement(self):
        material=self.paper();old=material_units(material)[0]['id']
        material.title='另一个资料名称';self.assertEqual(material_units(material)[0]['id'],old)
        material.text_content+='新增内容';self.assertNotEqual(material_units(material)[0]['id'],old)
        material.text_content=material.text_content[:-4]
        material.created_at+=timedelta(seconds=1)
        self.assertNotEqual(material_units(material)[0]['id'],old)

    def test_library_links_multiple_points_without_claiming_keyword_is_verified(self):
        material=self.paper()
        result=AnalysisResult(knowledge_points=[KnowledgePoint(name='极限',weight=.9),KnowledgePoint(name='第一小问',weight=.7)])
        items=library([material],result)
        links=items[0]['knowledge_points']
        self.assertEqual({p['name'] for p in links},{'极限','第一小问'})
        self.assertTrue(all(p['method']=='keyword' for p in links))
        self.assertNotIn('text',items[0])

    def test_forged_and_context_clipped_source_ids_are_discarded(self):
        material=self.material('\n'.join(f'{i}. 极限'+('内容'*100) for i in range(1,81)))
        material.source_type='历年题';self.db.commit()
        units=material_units(material)
        result=AnalysisResult(knowledge_points=[KnowledgePoint(name='极限',weight=.9,source_ids=[units[0]['id'],units[-1]['id'],'forged'])],review_plan=[PlanItem(day=1,date='2026-11-03',title='练习',source_ids=[units[1]['id']])])
        context=build_context([material])
        self.assertIn(units[0]['id'],context);self.assertNotIn(units[-1]['id'],context)
        attach_study_sources(result,[material])
        self.assertEqual(result.knowledge_points[0].source_ids,[units[0]['id']])
        self.assertEqual(result.review_plan[0].source_ids,[units[1]['id']])

    def test_owner_exam_analysis_and_stale_unit_access_checks(self):
        self.setup_routes();material=self.paper();unit=material_units(material)[0]
        analysis=self.analysis(material)
        path=f'/api/study-sources?exam_id={self.exam.id}&analysis_id={analysis.id}'
        self.assertEqual(self.client.get(path).status_code,200)
        self.assertEqual(self.client.get(path,headers={'x-user-id':str(self.peer.id)}).status_code,404)
        self.assertEqual(self.client.get(f'/api/study-sources?exam_id={self.other.id}&analysis_id={analysis.id}').status_code,404)
        params={'unit_id':unit['id']};url=f'/api/study-sources/{material.id}/unit'
        self.assertEqual(self.client.get(url,params=params).status_code,200)
        self.assertEqual(self.client.get(url,params=params,headers={'x-user-id':str(self.peer.id)}).status_code,404)
        material.text_content+='修改';self.db.commit()
        self.assertEqual(self.client.get(url,params=params).status_code,409)

    def test_pdf_page_image_and_original_download_are_private_and_bounded(self):
        self.setup_routes();material=self.paper();unit=material_units(material)[0]
        path=self.root/'test.pdf';writer=PdfWriter();writer.add_blank_page(300,400);writer.write(path)
        material.file_path=str(path);self.db.commit()
        url=f'/api/study-sources/{material.id}/original'
        with patch.object(study_sources,'UPLOAD_DIR',self.root):
            response=self.client.get(url,params={'unit_id':unit['id'],'page':1})
            self.assertEqual(response.status_code,200,response.text[:100])
            self.assertTrue(response.content.startswith(b'\x89PNG'))
            self.assertEqual(response.headers['cache-control'],'private, no-store')
            self.assertEqual(self.client.get(url,params={'unit_id':unit['id'],'page':2}).status_code,422)
            download=self.client.get(url,params={'download':True})
            self.assertTrue(download.content.startswith(b'%PDF'))
            self.assertIn('attachment',download.headers['content-disposition'])
            self.assertEqual(self.client.get(url,params={'revision':'0'*64}).status_code,409)
        # A database path outside the uploads root cannot expose another local file.
        self.assertEqual(self.client.get(url).status_code,404)

    def test_targeted_qa_includes_selected_source_and_rejects_forgery_before_model(self):
        self.setup_routes();material=self.paper();unit=material_units(material)[0]
        conversation=self.client.post('/api/ai/qa/conversations',json={'exam_id':self.exam.id}).json()
        path=f"/api/ai/qa/conversations/{conversation['id']}/messages"
        with patch.object(ai.settings,'LLM_MOCK',False),patch.object(ai,'chat_text',return_value='按原题条件给出的提示。') as model:
            payload=dict(content='请给提示',source_material_id=material.id,source_unit_id=unit['id'])
            response=self.client.post(path,json=payload)
            self.assertEqual(response.status_code,200,response.text)
            self.assertIn('本次指定来源',model.call_args.args[0])
            self.assertIn('第二小问',model.call_args.args[0])
            model.reset_mock()
            self.assertEqual(self.client.post(path,json={**payload,'source_unit_id':'forged'}).status_code,409)
            foreign=self.material(owner=self.peer,exam=self.peer_exam)
            self.assertEqual(self.client.post(path,json={**payload,'source_material_id':foreign.id}).status_code,404)
            model.assert_not_called()

    def test_task_sources_survive_capacity_split_edit_and_schema_replay(self):
        self.setup_routes();material=self.paper();unit=material_units(material)[0]
        row=Task(user_id=self.owner.id,exam_id=self.exam.id,title='极限练习',knowledge_point='极限',source_ids=[unit['id']],plan_date=self.exam.exam_date-timedelta(days=2),estimated_minutes=120,source='ai')
        self.db.add(row);self.db.commit()
        first=row.plan_date.isoformat();second=(row.plan_date+timedelta(days=1)).isoformat()
        study_planner.apply(self.db,self.owner.id,{'conflicts':[],'assignments':[{'task_id':row.id,'date':first,'minutes':60},{'task_id':row.id,'date':second,'minutes':60}]})
        self.assertEqual([t.source_ids for t in self.db.query(Task).all()],[[unit['id']],[unit['id']]])
        response=self.client.put(f'/api/tasks/{row.id}',json={'title':'重命名练习'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['source_ids'],[unit['id']])
        upgrade_schema(self.engine);upgrade_schema(self.engine)
        self.db.expire_all()
        self.assertEqual(self.db.get(Task,row.id).source_ids,[unit['id']])

    def test_manual_task_cannot_attach_sources_from_another_exam(self):
        self.setup_routes();material=self.material(exam=self.other);unit=material_units(material)[0]
        response=self.client.post('/api/tasks',json=dict(exam_id=self.exam.id,title='练习',plan_date=self.exam.exam_date.isoformat(),source_ids=[unit['id']]))
        self.assertEqual(response.status_code,422,response.text)

    def test_difficult_marks_deduplicate_by_source_version_and_keep_original(self):
        self.setup_routes();material=self.paper();unit=material_units(material)[0]
        path=f'/api/study-sources/{material.id}/difficult'
        payload={'unit_id':unit['id'],'knowledge_point':'极限'}
        first=self.client.post(path,json=payload)
        self.assertEqual(first.status_code,200,first.text)
        self.assertTrue(first.json()['added'])
        self.assertFalse(self.client.post(path,json=payload).json()['added'])
        self.assertEqual(self.client.post(path,json=payload,headers={'x-user-id':str(self.peer.id)}).status_code,404)
        material.text_content+='新的题目内容';self.db.commit()
        self.assertEqual(self.client.post(path,json=payload).status_code,409)
        new=material_units(material)[0]
        second=self.client.post(path,json={**payload,'unit_id':new['id']})
        self.assertTrue(second.json()['added'])
        self.assertNotEqual(first.json()['id'],second.json()['id'])
        rows=self.client.get('/api/collections').json()
        saved=json.loads(rows[0]['content'])
        self.assertEqual(saved['source_reference']['id'],new['id'])
        self.assertIn('第一小问',saved['question'])

    def test_background_job_preserves_target_source_through_execution(self):
        from sqlalchemy.orm import sessionmaker
        from app.services import ai_jobs
        self.setup_routes();self.client.app.include_router(jobs.router,prefix='/api/ai')
        material=self.paper();unit=material_units(material)[0]
        conversation=self.client.post('/api/ai/qa/conversations',json={'exam_id':self.exam.id}).json()
        payload=dict(kind='qa',request_key='source-job',payload=dict(conversation_id=conversation['id'],content='给提示',source_material_id=material.id,source_unit_id=unit['id']))
        with patch.object(ai_jobs,'enqueue'):
            submitted=self.client.post('/api/ai/jobs',json=payload)
        self.assertEqual(submitted.status_code,202,submitted.text)
        job_id=submitted.json()['id'];self.db.expire_all()
        stored=json.loads(self.db.get(AIJob,job_id).payload_json)
        self.assertEqual(stored['source_unit_id'],unit['id'])
        with patch.object(ai,'ask_qa',return_value={'messages':[]}) as qa:
            ai_jobs.execute(sessionmaker(bind=self.engine),job_id)
        self.assertEqual(qa.call_args.args[1].source_unit_id,unit['id'])
        self.assertEqual(qa.call_args.args[1].source_material_id,material.id)
        self.assertEqual(self.client.get(f'/api/ai/jobs/{job_id}').json()['status'],'succeeded')
