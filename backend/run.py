"""完整应用启动入口；从任意目录调用，保留原配置与数据。"""
import argparse
import json
import os
import sys
from pathlib import Path


def main():
    if hasattr(sys.stdout,'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='期末周别慌：同源页面与真实后端')
    parser.add_argument('--check',action='store_true',help='只检查，不创建目录、数据库或密钥')
    parser.add_argument('--api-only',action='store_true',help='仅启动后端，供独立Vite开发')
    parser.add_argument('--dev',action='store_true',help='启用开发热重载')
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=8000)
    parser.add_argument('--frontend-dir',type=Path,default=Path(__file__).resolve().parent.parent/'frontend'/'dist-app')
    args = parser.parse_args()
    if not 1<=args.port<=65535:
        parser.error('端口必须在1到65535之间')
    try:
        import uvicorn
        from app.config import settings
        from app.runtime import check, prepare
        frontend = None if args.api_only else args.frontend_dir.resolve()
        result = check(settings,frontend)
        print(json.dumps(result,ensure_ascii=False),flush=True)
        if not result['ok']:
            return 1
        if args.check:
            return 0
        prepare(settings)
    except ImportError:
        print('后端依赖未安装，请先运行项目根目录的start.ps1，或安装backend/requirements.lock.txt')
        return 1
    except Exception as exc:
        print('运行配置检查失败：'+(str(exc) if isinstance(exc,ValueError) and type(exc) is ValueError else type(exc).__name__))
        return 1
    if frontend is not None:
        os.environ['FMZH_FRONTEND_DIR'] = str(frontend)
    else:
        os.environ.pop('FMZH_FRONTEND_DIR',None)
    uvicorn.run('app.main:app',host=args.host,port=args.port,reload=args.dev,
                app_dir=str(Path(__file__).resolve().parent))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
