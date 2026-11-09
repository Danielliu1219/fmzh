"""兼容已有 SQLite 数据：补列和索引，保留分钟数并解绑历史孤立考试引用。"""
from uuid import uuid4
from contextlib import nullcontext

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from .mistakes import question_key
from ..models.models import Collection, Task, User, FocusSession, OperationLog, QaMessage


LEGACY_ACCOUNT_COLUMNS = {
    'users': {
        'class_name': "VARCHAR(32) NOT NULL DEFAULT ''",
        'avatar': "VARCHAR(16) NOT NULL DEFAULT ''",
        'is_admin': 'BOOLEAN NOT NULL DEFAULT 0',
        'is_banned': 'BOOLEAN NOT NULL DEFAULT 0',
        'failed_attempts': 'INTEGER NOT NULL DEFAULT 0',
        'locked_until': 'DATETIME',
    },
    'exams': {'color': "VARCHAR(16) NOT NULL DEFAULT ''", 'exam_time': 'TIME'},
    'courses': {'color': "VARCHAR(16) NOT NULL DEFAULT ''", 'is_active': 'BOOLEAN NOT NULL DEFAULT 1'},
}


def upgrade_schema(engine):
    with (nullcontext(engine) if isinstance(engine,Connection) else engine.begin()) as conn:
        # create_all只补缺表；旧账号/考试表也必须显式补齐后来新增的字段。
        for table, additions in LEGACY_ACCOUNT_COLUMNS.items():
            if not inspect(conn).has_table(table):
                continue
            columns = {c['name'] for c in inspect(conn).get_columns(table)}
            for name, sql_type in additions.items():
                if name not in columns:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {sql_type}'))
        if inspect(conn).has_table('qa_messages'):
            columns = {c['name'] for c in inspect(conn).get_columns('qa_messages')}
            for name, sql_type in {'source_unit_id': 'VARCHAR(160)', 'source_help_kind': 'VARCHAR(16)'}.items():
                if name not in columns:
                    conn.execute(text(f'ALTER TABLE qa_messages ADD COLUMN {name} {sql_type}'))
            next(i for i in QaMessage.__table__.indexes if i.name == 'ix_qa_messages_source_unit_id').create(conn, checkfirst=True)
        if inspect(conn).has_table('tasks'):
            columns = {c['name'] for c in inspect(conn).get_columns('tasks')}
            additions = {
                'start_time': 'TIME', 'end_time': 'TIME',
                'location': "VARCHAR(120) NOT NULL DEFAULT ''",
                'difficulty': "VARCHAR(16) NOT NULL DEFAULT 'medium'",
                'detail': "TEXT NOT NULL DEFAULT ('')",
                'knowledge_point': "VARCHAR(128) NOT NULL DEFAULT ''",
                'source_ids_json': "TEXT NOT NULL DEFAULT ('[]')",
                'repeat_rule': "VARCHAR(16) NOT NULL DEFAULT 'none'",
                'repeat_until': 'DATE', 'repeat_group_id': 'VARCHAR(32)',
            }
            for name, sql_type in additions.items():
                if name not in columns:
                    conn.execute(text(f'ALTER TABLE tasks ADD COLUMN {name} {sql_type}'))
            for index in Task.__table__.indexes:
                if index.name == 'ix_tasks_repeat_group_id':
                    index.create(conn, checkfirst=True)
        if inspect(conn).has_table('operation_logs'):
            if 'request_id' not in {c['name'] for c in inspect(conn).get_columns('operation_logs')}:
                conn.execute(text("ALTER TABLE operation_logs ADD COLUMN request_id VARCHAR(32) NOT NULL DEFAULT ''"))
            next(i for i in OperationLog.__table__.indexes if i.name == 'ix_operation_logs_request_id').create(conn,checkfirst=True)
        for table, name in [('daily_pressure_records','raw_score'), ('mood_records','composite_raw')]:
            if inspect(conn).has_table(table) and name not in {c['name'] for c in inspect(conn).get_columns(table)}:
                conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} FLOAT'))
        if inspect(conn).has_table("focus_sessions"):
            columns = {c["name"] for c in inspect(conn).get_columns("focus_sessions")}
            if "subject_snapshot" not in columns:
                conn.execute(text("ALTER TABLE focus_sessions ADD COLUMN subject_snapshot VARCHAR(64) NOT NULL DEFAULT ''"))
            if 'request_id' not in columns:
                conn.execute(text('ALTER TABLE focus_sessions ADD COLUMN request_id VARCHAR(64)'))
            next(i for i in FocusSession.__table__.indexes if i.name == 'uq_focus_user_request').create(conn, checkfirst=True)
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
            if 'parse_request_id' not in columns:
                conn.execute(text("ALTER TABLE materials ADD COLUMN parse_request_id VARCHAR(32) NOT NULL DEFAULT ''"))
            if 'parse_error' not in columns:
                conn.execute(text("ALTER TABLE materials ADD COLUMN parse_error VARCHAR(256) NOT NULL DEFAULT ''"))
            if 'file_size' not in columns:
                conn.execute(text('ALTER TABLE materials ADD COLUMN file_size INTEGER NOT NULL DEFAULT 0'))
                from pathlib import Path
                for row in (conn.execute(text('SELECT id,file_path FROM materials')).all() if 'file_path' in columns else []):
                    try: size=Path(row.file_path).stat().st_size
                    except OSError: size=0
                    conn.execute(text('UPDATE materials SET file_size=:size WHERE id=:id'),dict(size=size,id=row.id))
            if "text_locations" not in columns:
                conn.execute(text("ALTER TABLE materials ADD COLUMN text_locations TEXT NOT NULL DEFAULT ('[]')"))
            if "weight" not in columns:
                conn.execute(text("ALTER TABLE materials ADD COLUMN weight FLOAT"))
            for source, weight in DEFAULT_SOURCE_WEIGHT.items():
                conn.execute(text("UPDATE materials SET weight=:weight WHERE source_type=:source AND weight IS NULL"), {"source": source, "weight": weight})
            conn.execute(text("UPDATE materials SET weight=:weight WHERE weight IS NULL"), {"weight": DEFAULT_WEIGHT})
            for name in ('description', 'tags', 'text_content'):
                if name in columns:
                    conn.execute(text(f"UPDATE materials SET {name}='' WHERE {name} IS NULL"))
        if inspect(conn).has_table("user_profiles"):
            columns = {c["name"] for c in inspect(conn).get_columns("user_profiles")}
            if "target_band" not in columns:
                conn.execute(text("ALTER TABLE user_profiles ADD COLUMN target_band VARCHAR(8)"))
        columns = {c["name"] for c in inspect(conn).get_columns("users")}
        if 'student_no' in columns:
            if 'student_no_key' not in columns:
                conn.execute(text('ALTER TABLE users ADD COLUMN student_no_key VARCHAR(32)'))
            rows = conn.execute(text('SELECT id, student_no, student_no_key FROM users ORDER BY id')).all()
            claimed = {row.student_no_key for row in rows if row.student_no_key}
            for row in rows:
                number = (row.student_no or '').strip()
                if number and not row.student_no_key and number not in claimed:
                    conn.execute(text('UPDATE users SET student_no_key=:number WHERE id=:id'),dict(number=number,id=row.id))
                    claimed.add(number)
            next(i for i in User.__table__.indexes if i.name == 'uq_users_student_no_key').create(conn, checkfirst=True)
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
