"""本机加密备份与隔离恢复：密钥单独保存，恢复只写全新目录。"""

import json
import hashlib
import logging
import os
import sqlite3
import tempfile
import zipfile
from datetime import date, datetime, time, timezone, timedelta
from pathlib import Path, PurePosixPath
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from sqlalchemy import Date, DateTime, Time, create_engine, select, text
from ..database import Base
from ..models.models import User

MAGIC = b"FMZHBACKUP1"
logger = logging.getLogger(__name__)


def database_namespace(engine):
    # 同一目录内的不同数据库不能互相充当“最近备份”。URL默认隐藏密码。
    return hashlib.sha256(str(engine.url).encode()).hexdigest()[:16]


def key_bytes(path, *, create=False):
    path = Path(path)
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "wb") as stream:
                stream.write(os.urandom(32))
    key = path.read_bytes()
    if len(key) != 32:
        raise ValueError("备份密钥必须为32字节，不能自动覆盖已有密钥")
    return key


def encrypt(source, destination, key):
    nonce = os.urandom(12)
    enc = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    enc.authenticate_additional_data(MAGIC)
    with open(source, "rb") as src, open(destination, "xb") as dst:
        dst.write(MAGIC + nonce)
        while chunk := src.read(1024 * 1024):
            dst.write(enc.update(chunk))
        dst.write(enc.finalize())
        dst.write(enc.tag)


def decrypt(source, destination, key):
    with open(source, "rb") as src:
        if src.read(len(MAGIC)) != MAGIC:
            raise ValueError("备份格式不正确")
        nonce = src.read(12)
        src.seek(-16, 2)
        tag = src.read(16)
        remaining = src.tell() - 16 - len(MAGIC) - 12
        src.seek(len(MAGIC) + 12)
        dec = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
        dec.authenticate_additional_data(MAGIC)
        with open(destination, "xb") as dst:
            while remaining > 0:
                chunk = src.read(min(remaining, 1024 * 1024))
                if not chunk:
                    raise ValueError("备份不完整")
                remaining -= len(chunk)
                dst.write(dec.update(chunk))
            dst.write(dec.finalize())  # 认证失败不允许解包。


def snapshot(engine, upload_root, directory, key_file, session_secret):
    root = Path(upload_root).resolve()
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    key = key_bytes(key_file, create=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = directory / f"fmzh-{database_namespace(engine)}-{stamp}.enc"
    guard = None
    with tempfile.TemporaryDirectory(prefix="fmzh-backup-", dir=directory) as temporary:
        temporary = Path(temporary)
        archive = temporary / "snapshot.zip"
        try:
            # SQLite的保留写锁阻止增删与文件清理；MySQL锁住用户行后读取一致快照。
            if engine.dialect.name == "sqlite":
                if engine.url.database in (None, "", ":memory:"):
                    raise ValueError("内存数据库不执行持久备份")
                guard = sqlite3.connect(engine.url.database, timeout=30)
                guard.execute("BEGIN IMMEDIATE")
            with engine.connect() as conn:
                if engine.dialect.name == "mysql":
                    conn = conn.execution_options(isolation_level="REPEATABLE READ")
                    conn.execute(
                        select(User.id).order_by(User.id).with_for_update()
                    ).all()
                tables = {
                    table.name: [
                        dict(row) for row in conn.execute(select(table)).mappings()
                    ]
                    for table in Base.metadata.sorted_tables
                }
                paths = {}
                for name in ("materials", "file_cleanup_jobs"):
                    for row in tables.get(name, []):
                        path = Path(row["file_path"]).resolve()
                        if not path.is_relative_to(root):
                            raise ValueError("资料路径超出上传目录")
                        paths[row["file_path"]] = (
                            "uploads/" + path.relative_to(root).as_posix()
                        )
                with zipfile.ZipFile(
                    archive, "w", compression=zipfile.ZIP_DEFLATED
                ) as zipped:
                    zipped.writestr(
                        "database.json",
                        json.dumps(
                            dict(schema=1, tables=tables, paths=paths),
                            default=str,
                            ensure_ascii=False,
                        ),
                    )
                    zipped.writestr(".runtime/session.key", session_secret)
                    for original, relative in paths.items():
                        path = Path(original)
                        if path.is_file():
                            zipped.write(path, relative)
                        elif any(
                            r["file_path"] == original for r in tables["materials"]
                        ):
                            raise ValueError("数据库引用的资料文件缺失")
        finally:
            if guard is not None:
                guard.rollback()
                guard.close()
        pending = temporary / "encrypted.tmp"
        encrypt(archive, pending, key)
        pending.replace(output)
    return output


def restore(archive, key_file, destination):
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError("恢复目录必须是不存在的新目录，禁止覆盖当前数据")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="fmzh-restore-", dir=destination.parent
    ) as temporary:
        staging = Path(temporary)
        plain = staging / "snapshot.zip"
        data = staging / "data"
        data.mkdir()
        decrypt(archive, plain, key_bytes(key_file))
        with zipfile.ZipFile(plain) as zipped:
            for info in zipped.infolist():
                path = PurePosixPath(info.filename)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or "\\" in info.filename
                    or ":" in info.filename
                ):
                    raise ValueError("备份包含非法路径")
            record = json.loads(zipped.read("database.json"))
            if record.get("schema") != 1 or set(record["tables"]) != set(
                Base.metadata.tables
            ):
                raise ValueError("备份结构与当前程序不匹配")
            zipped.extractall(data)
        (data / "database.json").unlink()
        (data / "uploads").mkdir(exist_ok=True)
        target = create_engine("sqlite:///" + str(data / "fmzh.db"))
        try:
            Base.metadata.create_all(target)
            with target.begin() as conn:
                for table in Base.metadata.sorted_tables:
                    rows = record["tables"][table.name]
                    for row in rows:
                        for column in table.columns:
                            value = row.get(column.name)
                            if value is not None and isinstance(
                                column.type, (DateTime, Date, Time)
                            ):
                                parser = (
                                    datetime
                                    if isinstance(column.type, DateTime)
                                    else time
                                    if isinstance(column.type, Time)
                                    else date
                                )
                                row[column.name] = parser.fromisoformat(value)
                        if table.name in ("materials", "file_cleanup_jobs"):
                            row["file_path"] = str(
                                destination / record["paths"][row["file_path"]]
                            )
                    for offset in range(0, len(rows), 100):
                        conn.execute(table.insert(), rows[offset : offset + 100])
            with target.connect() as conn:
                if conn.execute(text("PRAGMA foreign_key_check")).all():
                    raise ValueError("恢复后的外键检查失败")
                if conn.scalar(text("PRAGMA integrity_check")) != "ok":
                    raise ValueError("恢复后的完整性检查失败")
        finally:
            target.dispose()
        data.rename(destination)
    return destination


def runner(engine, upload_root, settings):
    db = (
        Path(engine.url.database).resolve()
        if engine.dialect.name == "sqlite"
        and engine.url.database not in (None, "", ":memory:")
        else None
    )
    from ..config import BASE_DIR

    parent = db.parent if db else BASE_DIR
    directory = (
        Path(settings.BACKUP_DIR).resolve()
        if settings.BACKUP_DIR
        else parent / ".backups"
    )
    key_file = (
        Path(settings.BACKUP_KEY_FILE).resolve()
        if settings.BACKUP_KEY_FILE
        else parent / ".runtime" / "backup.key"
    )

    def due():
        if not settings.BACKUP_ENABLED or (
            engine.dialect.name == "sqlite" and db is None
        ):
            return {"enabled": False}
        try:
            latest = (
                max(
                    directory.glob(f"fmzh-{database_namespace(engine)}-*.enc"),
                    default=None,
                )
                if directory.exists()
                else None
            )
            if latest and datetime.now(timezone.utc) - datetime.fromtimestamp(
                latest.stat().st_mtime, timezone.utc
            ) < timedelta(hours=settings.BACKUP_INTERVAL_HOURS):
                return dict(
                    enabled=True,
                    ok=True,
                    last_backup_at=datetime.fromtimestamp(
                        latest.stat().st_mtime, timezone.utc
                    ).isoformat(),
                )
            output = snapshot(
                engine, upload_root, directory, key_file, settings.SECRET_KEY
            )
            return dict(
                enabled=True,
                ok=True,
                last_backup_at=datetime.fromtimestamp(
                    output.stat().st_mtime, timezone.utc
                ).isoformat(),
            )
        except Exception as exc:
            logger.error("backup failed exception=%s", type(exc).__name__)
            return dict(
                enabled=True,
                ok=False,
                error="自动备份失败，请检查服务器备份目录、密钥和资料完整性",
            )

    return due
