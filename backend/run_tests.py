"""隔离付费配置运行回归：python run_tests.py [-p test_study_sources.py]。"""
import argparse
import os
from pathlib import Path
import sys
import unittest

# 必须早于任何app模块导入，避免测试继承开发者.env中的付费Key。
os.environ['LLM_MOCK'] = 'true'
os.environ['DEEPSEEK_API_KEY'] = 'tests-only-no-billing'
os.environ['DEEPSEEK_BASE_URL'] = 'http://127.0.0.1:9'
os.environ['SECRET_KEY'] = 'unit-tests-only-session-secret-at-least-32-characters'


def local_network_only(event, args):
    if event == 'socket.connect':
        address = args[1]
        if isinstance(address, tuple) and address[0] not in ('127.0.0.1', '::1', 'localhost'):
            raise RuntimeError('回归测试禁止连接外部地址，请使用本地假上游')


sys.addaudithook(local_network_only)
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-p', '--pattern', default='test_*.py')
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.discover(str(Path(__file__).resolve().parent/'tests'), pattern=args.pattern)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
