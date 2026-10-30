"""LLM_MOCK=false真实HTTP回环测试；只用本地上游和合成Key，不替换chat_json。"""
import json
import socket
import time
import unittest
from collections import deque
from contextlib import ExitStack
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from unittest.mock import patch

from sqlalchemy.orm import Session

from app.config import settings
from app.models.models import Analysis, Exam, Material, QaMessage, Task, UserProfile
from app.routers import ai, dashboard
from app.services import llm_client
import test_auth_quizzes as fixtures
import test_recommendation_strategy as strategy_fixtures


def envelope(content, reason='stop'):
    return {'choices':[{'message':{'role':'assistant','content':content},'finish_reason':reason}]}


class LocalUpstream:
    def __init__(self):
        self.responses=deque()
        self.requests=[]
        outer=self
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                outer.requests.append({'path':self.path,'body':body,'authorization':self.headers.get('Authorization')})
                item=outer.responses.popleft() if outer.responses else {'status':500,'payload':{'error':'unplanned test call'}}
                time.sleep(item.get('delay',0))
                data=item.get('raw',json.dumps(item.get('payload',{}),ensure_ascii=False).encode())
                try:
                    self.send_response(item.get('status',200))
                    self.send_header('Content-Type','application/json')
                    self.send_header('Content-Length',str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):
                    pass
            def log_message(self,*args):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.server.daemon_threads=True
        self.thread=Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}/v1/'

    def add(self,content=None,**extra):
        self.responses.append({'payload':envelope(content),**extra})

    def close(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)


class LlmTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.upstream=LocalUpstream()
    @classmethod
    def tearDownClass(cls):cls.upstream.close()

    def setUp(self):
        fixtures.AuthQuizTests.setUp(self)
        self.stack=ExitStack()
        for name,value in [('LLM_MOCK',False),('DEEPSEEK_BASE_URL',self.upstream.url),('DEEPSEEK_API_KEY','qa-local-only')]:
            self.stack.enter_context(patch.object(settings,name,value))
        self.upstream.responses.clear();self.upstream.requests.clear()
        self.client.app.include_router(dashboard.router,prefix='/api')
        with Session(self.engine) as db:
            db.add(Exam(id=1,user_id=1,subject='数学',exam_date=date.today()+timedelta(days=14)))
            db.add(UserProfile(user_id=1,exam_id=1,raw_text='原有画像',target='medium',target_band='B+',learning_status='medium',available_days=5,daily_hours=2,is_complete=True))
            db.add(Material(user_id=1,exam_id=1,title='测试资料',file_path='only-local-test.txt',file_type='txt',source_type='老师重点',text_content='极限和积分的概念与计算练习。',parse_status='done'))
            db.add(Task(user_id=1,exam_id=1,title='原有任务',plan_date=date.today(),estimated_minutes=30,source='ai'))
            db.commit()

    def tearDown(self):
        self.stack.close()
        fixtures.AuthQuizTests.tearDown(self)

    register=fixtures.AuthQuizTests.register
    call=fixtures.AuthQuizTests.call

    def state(self):
        with Session(self.engine) as db:
            return {'analyses':[(r.id,r.result_json) for r in db.query(Analysis).order_by(Analysis.id)],
                    'tasks':[(r.id,r.title,r.plan_date,r.estimated_minutes,r.is_done) for r in db.query(Task).order_by(Task.id)],
                    'profiles':[(r.id,r.raw_text,r.target,r.available_days) for r in db.query(UserProfile).order_by(UserProfile.id)],
                    'messages':[(r.id,r.role,r.content) for r in db.query(QaMessage).order_by(QaMessage.id)]}

    def result(self):return strategy_fixtures.analysis().model_dump_json()

    def test_wire_contract_trailing_slash_json_and_text_history(self):
        self.upstream.add('{"ok":true}')
        self.assertEqual(llm_client.chat_json('system','question',321),{'ok':True})
        request=self.upstream.requests[-1]
        self.assertEqual(request['path'],'/v1/chat/completions')
        self.assertEqual(request['authorization'],'Bearer qa-local-only')
        self.assertEqual(request['body']['response_format'],{'type':'json_object'})
        self.assertEqual(request['body']['max_tokens'],321)
        self.assertEqual(request['body']['model'],settings.DEEPSEEK_MODEL)
        history=[{'role':'user','content':'第一问'},{'role':'assistant','content':'第一答'},{'role':'user','content':'继续'}]
        self.upstream.add('  第二答  ')
        self.assertEqual(llm_client.chat_text('system',history),'第二答')
        self.assertEqual(self.upstream.requests[-1]['body']['messages'][1:],history)
        self.assertNotIn('response_format',self.upstream.requests[-1]['body'])

    def test_invalid_response_shapes_json_arrays_and_truncation_are_recoverable(self):
        payloads=[[],{}, {'choices':[]},envelope(None),envelope({'not':'text'}),envelope('  '),envelope('[]'),envelope('{bad'),envelope('{}','length'),envelope('{"value":NaN}'),envelope('{"value":1e400}')]
        for payload in payloads:
            with self.subTest(payload=payload):
                self.upstream.responses.append({'payload':payload})
                with self.assertRaises(llm_client.LLMError):llm_client.chat_json('system','question')
        self.upstream.responses.append({'raw':b'{invalid'})
        with self.assertRaises(llm_client.LLMError):llm_client.chat_text('system',[])

    def test_upstream_http_status_does_not_leak_body_or_credentials(self):
        for status in (401,403,429,500,503):
            with self.subTest(status=status):
                self.upstream.add(status=status,raw=b'private-upstream-body qa-local-only')
                with self.assertRaises(llm_client.LLMError) as error:llm_client.chat_text('system',[])
                self.assertIn(str(status),str(error.exception))
                self.assertNotIn('private-upstream-body',str(error.exception))
                self.assertNotIn('qa-local-only',str(error.exception))

    def test_real_read_timeout_connection_failure_and_invalid_address(self):
        self.upstream.add('delayed',delay=.15)
        with patch.object(llm_client,'REQUEST_TIMEOUT',.02):
            with self.assertRaisesRegex(llm_client.LLMError,'超时'):llm_client.chat_text('system',[])
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
        with patch.object(settings,'DEEPSEEK_BASE_URL',f'http://127.0.0.1:{port}'):
            with self.assertRaises(llm_client.LLMError):llm_client.chat_text('system',[])
        with patch.object(settings,'DEEPSEEK_BASE_URL','http://127.0.0.1:invalid'):
            with self.assertRaises(llm_client.LLMError):llm_client.chat_text('system',[])

    def test_missing_key_fails_before_any_network_request(self):
        with patch.object(settings,'DEEPSEEK_API_KEY',''):
            with self.assertRaises(llm_client.LLMError):llm_client.chat_json('system','question')
        self.assertEqual(self.upstream.requests,[])

    def test_real_profile_http_success_persists_and_failure_preserves_previous(self):
        self.upstream.add(json.dumps({'target':'medium','learning_status':'medium','available_days':5,'daily_hours':2,'weak_chapters':['积分'],'output_need':[],'missing_fields':[]}))
        with patch.object(ai.prompts,'mock_extract_profile',side_effect=AssertionError('Mock path must not run')):
            self.call('POST','/ai/profile',{'exam_id':1,'raw_text':'更新后的画像描述'})
        before=self.state()
        self.upstream.add('[]')
        self.call('POST','/ai/profile',{'exam_id':1,'raw_text':'不应被保存'},status=502)
        self.assertEqual(before,self.state())

    def test_analysis_retries_bad_schema_then_persists_actual_tasks(self):
        self.upstream.add('{"knowledge_points":[{"weight":999}]}')
        self.upstream.add(self.result())
        with patch.object(ai.prompts,'mock_generate_analysis',side_effect=AssertionError('Mock path must not run')):
            result=self.call('POST','/ai/analyze',{'exam_id':1})
        self.assertEqual(len(self.upstream.requests),2)
        self.assertTrue(result['scheduling']['applied'])
        self.assertEqual(len(self.state()['analyses']),1)
        self.assertNotEqual(self.state()['tasks'][0][1],'原有任务')
        self.assertEqual(self.call('GET','/ai/analyses/1')['id'],result['id'])

    def test_profile_wrong_field_types_are_incomplete_instead_of_500(self):
        self.upstream.add(json.dumps({'target':{},'learning_status':[],'available_days':10**30,'daily_hours':100}))
        result=self.call('POST','/ai/profile',{'exam_id':1,'raw_text':'需要补全的描述'})
        self.assertFalse(result['is_complete'])
        self.assertIn('available_days',result['missing_fields'])
        self.assertIn('daily_hours',result['missing_fields'])

    def test_analysis_two_failures_keep_all_existing_data(self):
        before=self.state()
        self.upstream.add('{bad');self.upstream.add('[]')
        self.call('POST','/ai/analyze',{'exam_id':1},status=502)
        self.assertEqual(len(self.upstream.requests),2)
        self.assertEqual(before,self.state())

    def test_successful_http_with_failed_database_commit_rolls_back_everything(self):
        before=self.state();self.upstream.add(self.result())
        with patch('sqlalchemy.orm.Session.commit',side_effect=RuntimeError('injected commit failure')):
            response=self.client.post('/api/ai/analyze',headers=self.headers,json={'exam_id':1})
            self.assertEqual(response.status_code,500,response.text)
        self.assertEqual(before,self.state())

    def test_qa_success_and_upstream_failures_keep_history_atomic_and_login_valid(self):
        conversation=self.call('POST','/ai/qa/conversations',{'exam_id':1},status=201)
        path=f"/ai/qa/conversations/{conversation['id']}/messages"
        self.upstream.add('这是通过本机HTTP返回的回答。')
        result=self.call('POST',path,{'content':'解释积分'})
        self.assertEqual(len(result['messages']),2)
        before=self.state()
        for status in (401,429,503):
            self.upstream.add(status=status,raw=b'private upstream body')
            self.call('POST',path,{'content':'失败时不保留本条提问'},status=502)
            self.assertEqual(before,self.state())
            self.assertEqual(self.call('GET','/auth/me')['username'],'owner')

    def test_profile_timeout_returns_502_without_saving_partial_input(self):
        before=self.state()
        self.upstream.add('delayed',delay=.12)
        with patch.object(llm_client,'REQUEST_TIMEOUT',.02):
            result=self.call('POST','/ai/profile',{'exam_id':1,'raw_text':'超时内容不落库'},status=502)
        self.assertIn('超时',result['detail'])
        self.assertEqual(before,self.state())

    def test_weekly_report_uses_same_real_http_path(self):
        self.upstream.add('{"summary":"本机HTTP周报","subjects":[]}')
        response=self.client.post('/api/reports/weekly',headers=self.headers,json={})
        self.assertEqual(response.status_code,200,response.text)
        self.assertTrue(self.upstream.requests)
        self.upstream.add(status=503)
        response=self.client.post('/api/reports/weekly',headers=self.headers,json={})
        self.assertEqual(response.status_code,502,response.text)

    def test_weekly_wrong_subjects_shape_uses_existing_fallback_without_500(self):
        self.upstream.add('{"summary":"已有统计仍可使用","subjects":12}')
        response=self.client.post('/api/reports/weekly',headers=self.headers,json={})
        self.assertEqual(response.status_code,200,response.text)
