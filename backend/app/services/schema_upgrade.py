"""兼容已有 SQLite 数据：补列和索引，保留分钟数并解绑历史孤立考试引用。"""
from uuid import uuid4

from sqlalchemy import inspect, text

from .mistakes import question_key
from ..models.models import Collection


def upgrade_schema(engine):
    with engine.begin() as conn:
        if inspect(conn).has_table("focus_sessions"):
            columns = {c["name"] for c in inspect(conn).get_columns("focus_sessions")}
            if "subject_snapshot" not in columns:
                conn.execute(text("ALTER TABLE focus_sessions ADD COLUMN subject_snapshot VARCHAR(64) NOT NULL DEFAULT ''"))
            conn.execute(text("""UPDATE focus_sessions SET subject_snapshot = COALESCE(
                (SELECT subject FROM exams WHERE exams.id=focus_sessions.exam_id
                 AND exams.user_id=focus_sessions.user_id), '已删除考试')
                WHERE exam_id IS NOT NULL AND subject_snapshot = ''"""))
            conn.execute(text("""UPDATE focus_sessions SET exam_id=NULL WHERE exam_id IS NOT NULL
                AND NOT EXISTS (SELECT 1 FROM exams WHERE exams.id=focus_sessions.exam_id
                AND exams.user_id=focus_sessions.user_id)"""))
        if inspect(conn).has_table("materials"):
            from .material_weight import DEFAULT_SOURCE_WEIGHT, DEFAULT_WEIGHT
            columns = {c["name"] for c in inspect(conn).get_columns("materials")}
            if "text_locations" not in columns:
                conn.execute(text("ALTER TABLE materials ADD COLUMN text_locations TEXT NOT NULL DEFAULT '[]'"))
            if "weight" not in columns:
                conn.execute(text("ALTER TABLE materials ADD COLUMN weight FLOAT"))
            for source, weight in DEFAULT_SOURCE_WEIGHT.items():
                conn.execute(text("UPDATE materials SET weight=:weight WHERE source_type=:source AND weight IS NULL"), {"source": source, "weight": weight})
            conn.execute(text("UPDATE materials SET weight=:weight WHERE weight IS NULL"), {"weight": DEFAULT_WEIGHT})
        if inspect(conn).has_table("user_profiles"):
            columns = {c["name"] for c in inspect(conn).get_columns("user_profiles")}
            if "target_band" not in columns:
                conn.execute(text("ALTER TABLE user_profiles ADD COLUMN target_band VARCHAR(8)"))
        columns = {c["name"] for c in inspect(conn).get_columns("users")}
        if "auth_key" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN auth_key VARCHAR(64)"))
        for row in conn.execute(text("SELECT id FROM users WHERE auth_key IS NULL OR auth_key = ''")).all():
            conn.execute(text("UPDATE users SET auth_key=:key WHERE id=:id"), {"key": uuid4().hex, "id": row.id})

        columns = {c["name"] for c in inspect(conn).get_columns("collections")}
        if "question_key" not in columns:
            conn.execute(text("ALTER TABLE collections ADD COLUMN question_key VARCHAR(64)"))
            # 历史重复题保留原文，只给第一条建立去重键。
            seen = set()
            for row in conn.execute(text("SELECT id, user_id, title FROM collections WHERE item_type='question' ORDER BY id")).all():
                key = question_key(row.title)
                if (row.user_id, key) not in seen:
                    conn.execute(text("UPDATE collections SET question_key=:key WHERE id=:id"), {"key": key, "id": row.id})
                    seen.add((row.user_id, key))
        for index in Collection.__table__.indexes:
            if index.name == "uq_collections_user_question":
                index.create(conn, checkfirst=True)
