"""错题写入共用逻辑；事务由调用方提交，支持批内、跨次及并发去重。"""
from hashlib import sha256
import unicodedata

from sqlalchemy.exc import IntegrityError

from ..models.models import Collection


def normalized_title(title):
    return " ".join(unicodedata.normalize("NFKC", title).split())


def question_key(title):
    return sha256(normalized_title(title).encode("utf-8")).hexdigest()


def save_question(db, user_id, title, content, source="quiz"):
    title = normalized_title(title)
    key = question_key(title)
    existing = db.query(Collection).filter(Collection.user_id == user_id, Collection.question_key == key).first()
    if existing is not None:
        return existing, False
    item = Collection(user_id=user_id, item_type="question", title=title, content=content, source=source, question_key=key)
    try:
        with db.begin_nested():
            db.add(item)
            db.flush()
    except IntegrityError:
        existing = db.query(Collection).filter(Collection.user_id == user_id, Collection.question_key == key).first()
        if existing is None:
            raise
        return existing, False
    return item, True
