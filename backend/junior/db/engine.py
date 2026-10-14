"""Engine, sessions and database creation."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from junior.config import BACKEND_DIR, get_settings

log = logging.getLogger(__name__)


@lru_cache
def _engine_for(url: str) -> Engine:
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    return engine


def get_engine() -> Engine:
    return _engine_for(get_settings().database_url)


@contextmanager
def session_scope() -> Iterator[Session]:
    """A session that commits on success and rolls back on error."""
    session = sessionmaker(get_engine(), expire_on_commit=False)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", get_settings().database_url)
    return cfg


def init_db() -> None:
    """Create the database, or bring it up to the latest schema."""
    command.upgrade(alembic_config(), "head")
    log.info("Database ready at %s", get_settings().db_path)

