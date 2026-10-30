"""运行检查、持久化路径及同源前端托管；不修改.env或大模型配置。"""
import json
import os
import secrets
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.engine import make_url

from .config import BASE_DIR

DEFAULT_SECRET = 'dev-secret-key-change-me'


def database_url(value, base=BASE_DIR):
    url = make_url(value)
    if url.get_backend_name() == 'sqlite' and url.database not in (None, '', ':memory:'):
        url = url.set(database=(Path(base)/url.database).resolve().as_posix())
    return url


def database_path(value, base=BASE_DIR):
    url = database_url(value, base)
    return Path(url.database) if url.get_backend_name() == 'sqlite' and url.database not in (None, '', ':memory:') else None


def frontend_check(directory):
    root = Path(directory).resolve()
    try:
        manifest = json.loads((root/'app-build.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        raise ValueError('缺少完整应用构建，请先在frontend执行 npm run build:app')
    if manifest != {'schema':1, 'mode':'backend-api', 'base':'/'} or not (root/'index.html').is_file() or not (root/'assets').is_dir():
        raise ValueError('前端构建不是同源真实接口模式，请重新执行 npm run build:app')
    return root


def check(settings, frontend=None, base=BASE_DIR):
    db = database_path(settings.DATABASE_URL, base)
    upload = (Path(base)/settings.UPLOAD_DIR).resolve()
    issues = []
    for label, target in (('数据库目录',db.parent if db else None),('上传目录',upload)):
        if target is None:
            continue
        if target.exists() and not target.is_dir():
            issues.append(label+'不是文件夹')
            continue
        ancestor = next((p for p in (target,*target.parents) if p.exists()),None)
        if ancestor is None or not os.access(ancestor,os.W_OK):
            issues.append(label+'不可写')
    if db and db.exists() and (not db.is_file() or not os.access(db,os.W_OK)):
        issues.append('数据库文件不可写')
    secret_source = 'configured'
    if settings.SECRET_KEY == DEFAULT_SECRET:
        secret_source = 'automatic-on-start'
        if db is None:
            issues.append('当前数据库配置需要通过进程环境设置会话密钥')
        else:
            key_file = db.parent/'.runtime'/'session.key'
            if key_file.exists():
                try:
                    valid = len(key_file.read_text(encoding='utf-8').strip())>=32
                except (OSError,ValueError):
                    valid = False
                if not valid:
                    issues.append('持久化会话密钥文件不完整或不可读，请恢复有效备份')
                secret_source = 'persisted'
    if frontend is not None:
        try:
            frontend_check(frontend)
        except ValueError as exc:
            issues.append(str(exc))
    return dict(ok=not issues, frontend='same-origin' if frontend is not None else 'api-only',
                persistent_database=db is not None, llm_mode='mock' if settings.LLM_MOCK else 'real-unverified',
                session_secret=secret_source, issues=issues)


def prepare(settings, base=BASE_DIR):
    """仅启动时创建数据目录及首次会话密钥；已有自定义密钥保持原样。"""
    db = database_path(settings.DATABASE_URL, base)
    if db:
        db.parent.mkdir(parents=True,exist_ok=True)
    (Path(base)/settings.UPLOAD_DIR).resolve().mkdir(parents=True,exist_ok=True)
    if settings.SECRET_KEY == DEFAULT_SECRET:
        if db is None:
            raise ValueError('内存数据库请通过进程环境配置SECRET_KEY；不会创建临时会话密钥')
        key_file = db.parent/'.runtime'/'session.key'
        key_file.parent.mkdir(parents=True,exist_ok=True)
        try:
            descriptor = os.open(key_file,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(descriptor,'w',encoding='utf-8') as output:
                output.write(secrets.token_urlsafe(48))
        key = key_file.read_text(encoding='utf-8').strip()
        if len(key)<32:
            raise ValueError('持久化会话密钥文件不完整，请恢复有效备份；不会自动覆盖')
        settings.SECRET_KEY = key
        os.environ['SECRET_KEY'] = key


def cors_origins(served=False):
    value = os.environ.get('FMZH_CORS_ORIGINS')
    return [origin.strip() for origin in value.split(',') if origin.strip()] if value is not None else ([] if served else ['http://localhost:5173','http://127.0.0.1:5173'])


def attach_frontend(app, directory):
    root = frontend_check(directory)

    @app.api_route('/{path:path}',methods=['GET','HEAD'],include_in_schema=False)
    def frontend(path: str):
        if path.split('/',1)[0] in ('api','health','docs','redoc','openapi.json'):
            raise HTTPException(404,'接口不存在')
        target = (root/path).resolve()
        if not target.is_relative_to(root) or any(part.startswith('.') for part in Path(path).parts):
            raise HTTPException(404,'文件不存在')
        if target.is_file():
            return FileResponse(target,headers={'Cache-Control':'no-cache'} if target.name=='index.html' else {})
        if Path(path).suffix or path.startswith('assets/'):
            raise HTTPException(404,'文件不存在')
        return FileResponse(root/'index.html',headers={'Cache-Control':'no-cache'})
