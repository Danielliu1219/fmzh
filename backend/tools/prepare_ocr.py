"""准备本机中文/公式OCR模型。--check 仅离线检查，默认补齐缺失模型；--warm 额外加载引擎自检。"""
import argparse
from importlib.metadata import version
from pathlib import Path
import sys


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='离线检查模型文件，缺失时返回非零状态')
    parser.add_argument('--warm', action='store_true', help='额外加载OCR引擎做完整预热自检（约10–30秒）')
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    if args.check:
        def offline(event, arguments):
            if event == 'socket.connect':
                raise RuntimeError('离线检查发现缺失的模型，请去掉 --check 联网补齐')
        sys.addaudithook(offline)
    try:
        from app.services.pdf_recognition import ocr_engine, prepare_model_files
        print('正在检查本机中文、公式检测与公式转LaTeX组件。首次准备会下载开源模型。', flush=True)
        prepare_model_files(download=not args.check)
        if args.warm:
            ocr_engine()
            from pix2text.utils import data_dir
            print(f'本机公式OCR引擎加载正常，Pix2Text {version("pix2text")}，CPU推理。')
            print(f'公式模型缓存目录 {data_dir()}')
        else:
            print('本机公式OCR模型文件已就绪；后端启动时会自动预热。')
        return 0
    except ImportError as exc:
        print(f'OCR依赖缺失或版本不兼容，请按 backend/requirements.lock.txt 重新安装。相关组件 {exc.name}')
    except Exception as exc:
        print(f'模型准备未完成（{type(exc).__name__}）。请检查下载连接后重新运行本命令，已有模型会复用。')
        print(str(exc)[:800])
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
