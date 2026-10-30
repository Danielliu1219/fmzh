"""交付入口：只读检查、路径、持久化会话、同源SPA及接口边界。"""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app import runtime


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.settings=SimpleNamespace(DATABASE_URL='sqlite:///data/学习.db',UPLOAD_DIR='uploads',LLM_MOCK=True,SECRET_KEY=runtime.DEFAULT_SECRET)
        self.environment=patch.dict(os.environ)
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    def frontend(self):
        root=self.root/'frontend'
        (root/'assets').mkdir(parents=True)
        (root/'index.html').write_text('<html>真实接口应用</html>',encoding='utf-8')
        (root/'assets'/'app.js').write_text('export const app=true',encoding='utf-8')
        (root/'app-build.json').write_text(json.dumps({'schema':1,'mode':'backend-api','base':'/'}),encoding='utf-8')
        return root

    def test_relative_and_absolute_database_paths_and_query(self):
        self.assertEqual(runtime.database_path(self.settings.DATABASE_URL,self.root),self.root/'data'/'学习.db')
        absolute='sqlite:///'+(self.root/'absolute.db').as_posix()
        self.assertEqual(runtime.database_path(absolute,self.root),self.root/'absolute.db')
        self.assertEqual(runtime.database_url('sqlite:///data.db?timeout=15',self.root).query['timeout'],'15')
        self.assertIsNone(runtime.database_path('sqlite:///:memory:',self.root))

    def test_check_is_readonly_and_does_not_leak_secret(self):
        self.settings.SECRET_KEY='private-test-secret'
        before=list(self.root.rglob('*'))
        result=runtime.check(self.settings,base=self.root)
        self.assertTrue(result['ok'])
        self.assertEqual(before,list(self.root.rglob('*')))
        self.assertNotIn('private-test-secret',json.dumps(result))

    def test_default_session_secret_persists_across_starts(self):
        runtime.prepare(self.settings,self.root)
        key=self.settings.SECRET_KEY
        self.assertGreaterEqual(len(key),32)
        self.settings.SECRET_KEY=runtime.DEFAULT_SECRET
        runtime.prepare(self.settings,self.root)
        self.assertEqual(self.settings.SECRET_KEY,key)
        self.assertFalse((self.root/'.env').exists())
        self.assertFalse((self.root/'data'/'学习.db').exists())

    def test_custom_secret_is_preserved_without_generating_key(self):
        self.settings.SECRET_KEY='existing-custom-key'
        runtime.prepare(self.settings,self.root)
        self.assertEqual(self.settings.SECRET_KEY,'existing-custom-key')
        self.assertFalse((self.root/'data'/'.runtime').exists())

    def test_corrupt_secret_fails_without_replacing_it(self):
        key=self.root/'data'/'.runtime'/'session.key'
        key.parent.mkdir(parents=True)
        key.write_text('broken',encoding='utf-8')
        with self.assertRaises(ValueError):runtime.prepare(self.settings,self.root)
        self.assertEqual(key.read_text(encoding='utf-8'),'broken')
        self.assertFalse(runtime.check(self.settings,base=self.root)['ok'])

    def test_memory_database_does_not_silently_persist_a_key(self):
        self.settings.DATABASE_URL='sqlite:///:memory:'
        with self.assertRaises(ValueError):runtime.prepare(self.settings,self.root)
        self.assertFalse(runtime.check(self.settings,base=self.root)['persistent_database'])
        self.assertFalse(any(p.name=='session.key' for p in self.root.rglob('*')))

    def test_invalid_storage_and_frontend_are_actionable(self):
        (self.root/'uploads').write_text('not a directory',encoding='utf-8')
        result=runtime.check(self.settings,self.root/'missing',self.root)
        self.assertFalse(result['ok'])
        self.assertEqual(len(result['issues']),2)

    def test_pages_or_wrong_manifest_cannot_be_served_as_real_app(self):
        root=self.frontend()
        (root/'app-build.json').write_text('{"mode":"static-demo"}',encoding='utf-8')
        with self.assertRaises(ValueError):runtime.attach_frontend(FastAPI(),root)

    def test_spa_refresh_assets_and_api_boundaries(self):
        app=FastAPI()
        @app.get('/api/real')
        def real():return {'ok':True}
        runtime.attach_frontend(app,self.frontend())
        with TestClient(app) as client:
            self.assertIn('真实接口应用',client.get('/analysis').text)
            self.assertEqual(client.get('/api/real').json(),{'ok':True})
            self.assertEqual(client.get('/assets/app.js').status_code,200)
            for path in ('/api/missing','/assets/missing.js','/.env','/%2e%2e/private.txt'):
                response=client.get(path)
                self.assertEqual(response.status_code,404,path)
                self.assertIn('application/json',response.headers['content-type'])
            self.assertEqual(client.get('/').headers['cache-control'],'no-cache')
            self.assertEqual(client.head('/exams').status_code,200)

    def test_unexpected_origin_is_not_allowed(self):
        os.environ.pop('FMZH_CORS_ORIGINS',None)
        app=FastAPI()
        app.add_middleware(CORSMiddleware,allow_origins=runtime.cors_origins(False),allow_methods=['*'])
        with TestClient(app) as client:
            good=client.options('/api/test',headers={'Origin':'http://localhost:5173','Access-Control-Request-Method':'GET'})
            bad=client.options('/api/test',headers={'Origin':'https://unexpected.invalid','Access-Control-Request-Method':'GET'})
            self.assertEqual(good.status_code,200)
            self.assertNotIn('access-control-allow-origin',bad.headers)
        self.assertEqual(runtime.cors_origins(True),[])

    def test_cli_check_from_another_directory_creates_no_database_or_key(self):
        front=self.frontend()
        env={**os.environ,'DATABASE_URL':'sqlite:///'+(self.root/'fresh'/'app.db').as_posix(),'UPLOAD_DIR':str(self.root/'uploads'),'SECRET_KEY':runtime.DEFAULT_SECRET,'LLM_MOCK':'true'}
        result=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'run.py'),'--check','--frontend-dir',str(front)],cwd=self.root,env=env,capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertTrue(json.loads(result.stdout)['ok'])
        self.assertFalse((self.root/'fresh').exists())
        self.assertFalse((self.root/'uploads').exists())

    def test_invalid_configuration_does_not_print_input_values(self):
        env={**os.environ,'ACCESS_TOKEN_EXPIRE_MINUTES':'private-test-secret'}
        result=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'run.py'),'--check','--api-only'],cwd=self.root,env=env,capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(result.returncode,1)
        self.assertNotIn('private-test-secret',result.stdout+result.stderr)
