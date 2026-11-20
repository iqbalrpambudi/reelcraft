from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import DateTime, Engine, TypeDecorator, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session

from reelcraft.core.config import get_settings

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator[datetime]):
    """SQLite drops tzinfo: store naive UTC, always hand back aware UTC."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        return value.astimezone(UTC).replace(tzinfo=None) if value else value

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        return value.replace(tzinfo=UTC) if value else value


def utcnow() -> datetime:
    return datetime.now(UTC)


def alembic_config(url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _sqlite_pragmas(dbapi_conn: Any, _record: Any) -> None:
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")  # API and CLI can read while a job writes
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


@lru_cache
def get_engine() -> Engine:
    """Engine for the configured data dir, migrated to head on first use by any entry point."""
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(settings.database_url)
    event.listen(engine, "connect", _sqlite_pragmas)
    command.upgrade(alembic_config(settings.database_url), "head")
    return engine


@contextmanager
def session_scope() -> Iterator[Session]:
    """One unit of work: commit on success, roll back on error."""
    with Session(get_engine(), expire_on_commit=False) as session, session.begin():
        yield session
