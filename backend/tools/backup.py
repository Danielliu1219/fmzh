"""python tools/backup.py create；或 restore 备份文件 新目录 --key 密钥文件。"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.backups import restore
from app.database import engine
from app.config import settings, UPLOAD_DIR

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("create")
    command = commands.add_parser("restore")
    command.add_argument("archive", type=Path)
    command.add_argument("directory", type=Path)
    command.add_argument("--key", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "create":
            # 显式命令强制做一次，不等待24小时。
            from app.services.backups import snapshot
            from app.runtime import database_path, prepare
            from app.config import BASE_DIR

            prepare(settings)
            parent = (
                database_path(settings.DATABASE_URL) or (BASE_DIR / "placeholder")
            ).parent
            output = snapshot(
                engine,
                UPLOAD_DIR,
                settings.BACKUP_DIR or parent / ".backups",
                settings.BACKUP_KEY_FILE or parent / ".runtime" / "backup.key",
                settings.SECRET_KEY,
            )
        else:
            output = restore(args.archive, args.key, args.directory)
        print("已完成：" + str(output))
    except Exception as exc:
        print("未完成：" + type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)
