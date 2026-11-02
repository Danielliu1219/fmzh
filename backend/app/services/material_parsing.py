"""后台解析独立于HTTP响应；更新时重验资料身份，失败可重试。"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from ..models.models import Material, OperationLog, User
from .file_parser import parse_document
from .deletion import _upload_path

_pool = None
_pool_lock = Lock()
_active = {}
logger = logging.getLogger(__name__)


def enqueue(factory, material_id, root, request_id=""):
    global _pool
    with _pool_lock:
        for key in [key for key, future in _active.items() if future.done()]:
            _active.pop(key)
        key = (str(Path(root).resolve()), material_id)
        if key in _active:
            return False
        if _pool is None:
            _pool = ThreadPoolExecutor(
                max_workers=2, thread_name_prefix="material-parse"
            )
        _active[key] = _pool.submit(parse, factory, material_id, root, request_id)
        return True


def parse(factory, material_id, root, request_id=""):
    try:
        return _parse(factory, material_id, root, request_id)
    except Exception as exc:
        logger.error(
            "material parse failed request_id=%s material_id=%s exception=%s",
            request_id,
            material_id,
            type(exc).__name__,
        )


def _parse(factory, material_id, root, request_id=""):
    with factory() as db:
        item = db.get(Material, material_id)
        if item is None or item.parse_status != "pending":
            return
        uid, created, path, kind = (
            item.user_id,
            item.created_at,
            item.file_path,
            item.file_type,
        )
        request_id = request_id or item.parse_request_id
        user = db.get(User, uid)
        if user is None:
            return
        actor = user.username
    text, locations, error = "", [], ""
    try:
        path = _upload_path(path, Path(root))
        text, locations = parse_document(path, kind)
        if not text.strip():
            error = (
                "没有可识别文字，可能是扫描件或空文件；请换用清晰图片或文本版资料后重试"
            )
    except Exception:
        error = "解析失败，请检查文件内容后重试"
        if kind in ("png", "jpg", "jpeg"):
            error += "；首次图片识别需联网下载免费的本机识别模型"
    for attempt in range(3):
        try:
            with factory() as db:
                if (
                    not db.query(User)
                    .filter(User.id == uid)
                    .update({User.id: uid}, synchronize_session=False)
                ):
                    return
                item = (
                    db.query(Material)
                    .filter_by(
                        id=material_id,
                        user_id=uid,
                        created_at=created,
                        parse_status="pending",
                    )
                    .first()
                )
                if item is None:
                    return
                if not error:
                    item.text_content = text
                    item.text_locations = json.dumps(locations, ensure_ascii=False)
                item.parse_status = "failed" if error else "done"
                item.parse_error = error + (
                    "；上次成功解析的文字已保留" if error and item.text_content else ""
                )
                db.add(
                    OperationLog(
                        request_id=request_id,
                        actor_id=uid,
                        actor_name=actor,
                        action="material.parse",
                        target_id=str(material_id),
                        method="POST",
                        path="/api/materials",
                        status_code=422 if error else 200,
                        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
                    )
                )
                db.commit()
            return
        except Exception as exc:
            logger.error(
                "material parse persistence failed request_id=%s material_id=%s attempt=%s exception=%s",
                request_id,
                material_id,
                attempt + 1,
                type(exc).__name__,
            )


def recover(factory, root):
    with factory() as db:
        ids = [
            row[0]
            for row in db.query(Material.id).filter(Material.parse_status == "pending")
        ]
    for mid in ids:
        enqueue(factory, mid, root)


def stop():
    global _pool
    with _pool_lock:
        pool, _pool = _pool, None
    if pool:
        pool.shutdown(wait=True, cancel_futures=True)
