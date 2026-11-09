"""LLM_MOCK=false真实HTTP回环测试；只用本地上游和合成Key，不替换chat_json。"""
import json
import socket
import time
import unittest
import httpx
from collections import deque
from contextlib import ExitStack
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from unittest.mock import patch, AsyncMock

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
                heartbeats=item.get('heartbeats',0)
                try:
                    if 'events' in item:
                        self.send_response(200)
                        self.send_header('Content-Type', 'text/event-stream')
                        self.send_header('Connection', 'close')
                        self.end_headers()
                        self.close_connection = True
                        self.wfile.write(b': heartbeat\n\n')
                        for event in item['events']:
                            time.sleep(item.get('event_delay', .05))
                            text = event if isinstance(event, str) else json.dumps(event, ensure_ascii=False)
                            self.wfile.write(('data: ' + text + '\n\n').encode())
                            self.wfile.flush()
                        return
                    self.send_response(item.get('status',200))
                    self.send_header('Content-Type','application/json')
                    self.send_header('Content-Length',str(len(data)+heartbeats))
                    self.end_headers()
                    for _ in range(heartbeats):
                        self.wfile.write(b' ');self.wfile.flush();time.sleep(.02)
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

    def test_total_deadline_cannot_be_extended_by_upstream_heartbeat_bytes(self):
        self.upstream.add('answer after continuous heartbeats',heartbeats=50)
        with patch.object(llm_client,'REQUEST_TIMEOUT',.08):
            with self.assertRaisesRegex(llm_client.LLMError,'超时'):
                llm_client.chat_text('system',[])

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
            if status in (429,503): self.upstream.add(status=status,raw=b'private upstream body')
            self.call('POST',path,{'content':'失败时不保留本条提问'},status=502)
            self.assertEqual(before,self.state())
            self.assertEqual(self.call('GET','/auth/me')['username'],'owner')

    def test_profile_timeout_returns_502_without_saving_partial_input(self):
        before=self.state()
        self.upstream.add('delayed',delay=.12)
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
        self.upstream.add(status=503)
        response=self.client.post('/api/reports/weekly',headers=self.headers,json={})
        self.assertEqual(response.status_code,502,response.text)

    def test_weekly_wrong_subjects_shape_uses_existing_fallback_without_500(self):
        self.upstream.add('{"summary":"已有统计仍可使用","subjects":12}')
        response=self.client.post('/api/reports/weekly',headers=self.headers,json={})
        self.assertEqual(response.status_code,200,response.text)

    def test_profile_transient_timeout_retries_once_then_saves_valid_response(self):
        self.upstream.add('delayed',delay=.45)
        self.upstream.add(json.dumps({'target':'pass','learning_status':'weak','available_days':5,'daily_hours':2,'missing_fields':[]}))
        with patch.object(llm_client,'REQUEST_TIMEOUT',.2):
            result=self.call('POST','/ai/profile',{'exam_id':1,'raw_text':'重试后的有效画像'})
        self.assertEqual(result['target'],'pass')
        self.assertEqual(len(self.upstream.requests),2)

    def test_analysis_truncation_does_not_retry_or_replace_existing_plan(self):
        before = self.state()
        self.upstream.responses.append({'payload': envelope('{"course":"unfinished"', 'length')})
        response = self.call('POST', '/ai/analyze', {'exam_id': 1}, status=502)
        self.assertIn('未自动重试', response['detail'])
        self.assertEqual(len(self.upstream.requests), 1)
        self.assertEqual(before, self.state())

    def test_analysis_omits_output_cap_and_uses_its_own_wait_limit(self):
        content = json.loads(self.result())
        content['summary'] = '完整的复习建议。' * 600
        self.upstream.add(json.dumps(content, ensure_ascii=False), delay=.08)
        with patch.object(llm_client, 'REQUEST_TIMEOUT', .02):
            result = self.call('POST', '/ai/analyze', {'exam_id': 1})
        body = self.upstream.requests[-1]['body']
        self.assertNotIn('max_tokens', body)
        self.assertIn('完整的复习建议', result['result']['summary'])
        self.assertEqual(len(self.upstream.requests), 1)

    def test_profile_qa_and_weekly_all_omit_output_cap(self):
        self.upstream.add('{"target":"pass","learning_status":"weak","available_days":4,"daily_hours":2}')
        self.call('POST','/ai/profile',{'exam_id':1,'raw_text':'正常提取'})
        conversation=self.call('POST','/ai/qa/conversations',{'exam_id':1},status=201)
        self.upstream.add('完整的问答正文')
        self.call('POST',f"/ai/qa/conversations/{conversation['id']}/messages",{'content':'解释积分'})
        self.upstream.add('{"summary":"周报","subjects":[]}')
        self.call('POST','/reports/weekly',{})
        self.assertEqual(len(self.upstream.requests),3)
        for request in self.upstream.requests:
            self.assertNotIn('max_tokens',request['body'])
            self.assertNotIn('max_completion_tokens',request['body'])

    def test_deepseek_flash_keeps_thinking_enabled_without_external_request(self):
        response = httpx.Response(200, json=envelope('{"ok":true}'), request=httpx.Request('POST', 'https://api.deepseek.com/chat/completions'))
        # Mock transport first, then change host; never contact the real platform.
        with patch.object(llm_client, '_post_with_deadline', new_callable=AsyncMock, return_value=response) as post:
            with patch.object(settings, 'DEEPSEEK_BASE_URL', 'https://api.deepseek.com'), patch.object(settings, 'DEEPSEEK_MODEL', 'deepseek-flash'):
                self.assertEqual(llm_client.chat_json('fixed JSON system', 'question'), {'ok': True})
            self.assertEqual(post.call_args.args[1]['thinking'], {'type': 'enabled'})
        self.assertEqual(self.upstream.requests, [])

    def test_custom_total_deadline_still_stops_heartbeat_stream(self):
        self.upstream.add('{"ok":true}', heartbeats=30)
        with self.assertRaisesRegex(llm_client.LLMError, '超时'):
            llm_client.chat_json('system', 'question', timeout=.05)

    def test_streaming_delivers_partial_answer_before_completion_and_measures_first_content(self):
        self.upstream.responses.append({'events': [
            {'choices': [{'delta': {'reasoning_content': 'private reasoning'}}]},
            {'choices': [{'delta': {'content': '### 解答\n'}}]},
            {'choices': [{'delta': {'content': '分子求导：\n\\[x^2\\]'}}]},
            {'choices': [{'delta': {}, 'finish_reason': 'stop'}]},
            {'choices': [], 'usage': {'prompt_tokens': 10, 'completion_tokens': 20,
                'completion_tokens_details': {'reasoning_tokens': 12}}}, '[DONE]'], 'event_delay': .06})
        updates = []
        with self.assertLogs(llm_client.logger, level='INFO') as logs:
            with llm_client.progress_listener(lambda progress: updates.append((time.perf_counter(), progress))):
                answer = llm_client.chat_text('system', [{'role': 'user', 'content': '求导'}])
        finished = time.perf_counter()
        partial_time, partial = next((stamp, p) for stamp, p in updates if p.get('content') == '### 解答\n')
        self.assertGreater(finished - partial_time, .1)
        self.assertEqual(answer, '### 解答\n分子求导：\n\\[x^2\\]')
        self.assertGreater(partial['first_content_seconds'], 0)
        self.assertLessEqual(partial['first_response_seconds'], partial['first_content_seconds'])
        self.assertNotIn('private reasoning', json.dumps(updates))
        self.assertNotIn('private reasoning', '\n'.join(logs.output))
        body = self.upstream.requests[-1]['body']
        self.assertTrue(body['stream'])
        self.assertEqual(body['stream_options'], {'include_usage': True})

    def test_streaming_json_profile_uses_complete_content_before_saving(self):
        self.upstream.responses.append({'events': [
            {'choices': [{'delta': {'content': '{"target":"pass",'}}]},
            {'choices': [{'delta': {'content': '"learning_status":"weak","available_days":5,"daily_hours":2}'}}]},
            {'choices': [{'delta': {}, 'finish_reason': 'stop'}]}, '[DONE]']})
        result = self.call('POST', '/ai/profile', {'exam_id': 1, 'raw_text': '流式画像'})
        self.assertTrue(result['is_complete'])
        self.assertEqual(result['target'], 'pass')

    def test_unfinished_or_malformed_stream_does_not_save_messages_or_retry(self):
        conversation = self.call('POST', '/ai/qa/conversations', {'exam_id': 1}, status=201)
        path = f"/ai/qa/conversations/{conversation['id']}/messages"
        for events in ([{'choices': [{'delta': {'content': '半截回答'}}]}, '[DONE]'], ['malformed-json'],
                [{'choices': [{'delta': {'content': '截断'}, 'finish_reason': 'length'}]}, '[DONE]']):
            before = self.state()
            calls = len(self.upstream.requests)
            self.upstream.responses.append({'events': events})
            self.call('POST', path, {'content': '解释积分'}, status=502)
            self.assertEqual(self.state(), before)
            self.assertEqual(len(self.upstream.requests), calls + 1)

    def test_timeout_after_partial_stream_does_not_duplicate_billable_call(self):
        conversation = self.call('POST', '/ai/qa/conversations', {'exam_id': 1}, status=201)
        path = f"/ai/qa/conversations/{conversation['id']}/messages"
        self.upstream.responses.append({'events': [
            {'choices': [{'delta': {'content': '半截回答'}}]},
            {'choices': [{'delta': {'content': '延迟返回'}}]},
            {'choices': [{'delta': {}, 'finish_reason': 'stop'}]}], 'event_delay': .15})
        before = self.state()
        with patch.object(llm_client, 'REQUEST_TIMEOUT', .28):
            self.call('POST', path, {'content': '解释积分'}, status=502)
        self.assertEqual(len(self.upstream.requests), 1)
        self.assertEqual(self.state(), before)

    def test_analysis_partial_stream_failure_does_not_enter_schema_retry(self):
        self.upstream.responses.append({'events': [
            {'choices': [{'delta': {'content': '{"course":"半截分析"'}}]}, '[DONE]']})
        before = self.state()
        self.call('POST', '/ai/analyze', {'exam_id': 1}, status=502)
        self.assertEqual(len(self.upstream.requests), 1)
        self.assertEqual(self.state(), before)

    def test_job_progress_exposes_answer_but_omits_private_reasoning_and_profile_json(self):
        from types import SimpleNamespace
        from app.services import ai_jobs
        job = SimpleNamespace(id='progress-test', kind='qa', status='running', request_id='',
            result_json=None, error_message='', error_status=0)
        try:
            ai_jobs.update_progress(job.id, 'qa', dict(stage='answering', content='部分解答'))
            self.assertEqual(ai_jobs.output(job)['progress']['content'], '部分解答')
            ai_jobs.update_progress(job.id, 'qa', dict(stage='connecting', content=''))
            self.assertEqual(ai_jobs.output(job)['progress']['content'], '')
            self.assertNotIn('request_seconds', ai_jobs.output(job)['progress'])
            # 独立画像任务不把未校验 JSON 作为正文展示。
            ai_jobs.update_progress('profile-progress', 'profile', dict(stage='answering', content='{"target":"pass"}'))
            job.id = 'profile-progress'
            self.assertNotIn('content', ai_jobs.output(job)['progress'])
        finally:
            ai_jobs._progress.pop('progress-test', None)
            ai_jobs._progress.pop('profile-progress', None)


class ResponseStatsTests(unittest.TestCase):
    def test_usage_separates_reasoning_from_answer_without_recording_text(self):
        payload = envelope('private answer')
        payload['choices'][0]['message']['reasoning_content'] = 'private reasoning'
        payload['usage'] = {'prompt_tokens': 100, 'completion_tokens': 16000,
            'completion_tokens_details': {'reasoning_tokens': 15000}}
        stats = llm_client.response_stats(payload, 65536)
        self.assertEqual((stats['reasoning_tokens'], stats['answer_tokens']), (15000, 1000))
        self.assertNotIn('private', json.dumps(stats))
        self.assertEqual(stats['answer_chars'], len('private answer'))

    def test_missing_or_invalid_usage_does_not_invent_token_counts(self):
        for usage in (None, 'bad', {'completion_tokens': True}, {'completion_tokens': -1},
                {'completion_tokens': 10, 'completion_tokens_details': {'reasoning_tokens': 99}}):
            stats = llm_client.response_stats({'usage': usage, 'choices': []}, 65536)
            self.assertIsNone(stats['answer_tokens'])
            self.assertEqual(stats['finish_reason'], 'unknown')
