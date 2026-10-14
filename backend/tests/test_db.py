from datetime import timedelta

from alembic import command
from sqlalchemy import inspect, select

from junior.db import Conversation, Message, get_engine, init_db, session_scope
from junior.db.engine import alembic_config
from junior.db.models import utcnow

TABLES = {"conversations", "messages", "memories", "usage", "audit_log", "settings"}


def test_init_db_creates_all_tables(isolated_settings):
    init_db()
    assert isolated_settings.db_path.exists()
    assert TABLES <= set(inspect(get_engine()).get_table_names())


def test_init_db_is_safe_to_run_twice():
    init_db()
    init_db()


def test_migrations_match_models():
    """Fails if a model changed without a new Alembic migration."""
    init_db()
    command.check(alembic_config())


def test_deleting_a_conversation_deletes_its_messages():
    init_db()
    with session_scope() as s:
        convo = Conversation(title="Test")
        convo.messages.append(Message(role="user", source="user", content="hi"))
        s.add(convo)
    with session_scope() as s:
        s.delete(s.scalars(select(Conversation)).one())
    with session_scope() as s:
        assert s.scalars(select(Message)).all() == []


def test_times_come_back_in_utc():
    init_db()
    with session_scope() as s:
        s.add(Conversation(title="Time"))
    with session_scope() as s:
        created = s.scalars(select(Conversation)).one().created_at
    assert created.utcoffset() == timedelta(0)
    assert abs(utcnow() - created) < timedelta(seconds=5)
