"""Database engine, session factory and startup helpers.

init_db() creates any missing tables and, since there's no Alembic yet, also
adds any model columns missing from tables that already existed (see
_sync_schema and BACKLOG.md).
"""

from __future__ import annotations

import time
from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

engine = create_engine(settings.sqlalchemy_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    """FastAPI dependency that yields a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def wait_for_db(retries: int = 30, delay: float = 2.0) -> None:
    """Block until the database accepts connections (compose starts containers in parallel)."""
    last_err: Exception | None = None
    print(f"[startup] connecting to database at {settings.db_target}")
    for attempt in range(1, retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("[startup] database connection OK")
            return
        except OperationalError as err:  # pragma: no cover - timing dependent
            last_err = err
            print(f"[startup] database not ready (attempt {attempt}/{retries}): {err.orig}")
            time.sleep(delay)
    raise RuntimeError(
        f"database unreachable at {settings.db_target} after {retries} attempts"
    ) from last_err


def _sync_schema(target_engine: Engine) -> None:
    """Add model columns missing from already-existing tables.

    create_all() only creates tables that don't exist yet - it never alters
    one that's already there, so a nullable column added to a model here
    would otherwise never reach a table created by an earlier app version.
    Only additive, nullable columns are supported (see BACKLOG.md for
    adopting Alembic once real migrations - renames, backfills, drops - are
    needed).
    """
    inspector = inspect(target_engine)
    existing_tables = set(inspector.get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # create_all() will create it fresh, with every column
        existing_columns = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing_columns:
                continue
            assert column.nullable, f"{table.name}.{column.name}: only nullable columns can be auto-added"
            ddl_type = column.type.compile(dialect=target_engine.dialect)
            with target_engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {ddl_type}'))


def init_db() -> None:
    """Create tables and add any columns missing from existing ones."""
    from . import models  # noqa: F401  (register models on Base.metadata)

    Base.metadata.create_all(bind=engine)
    _sync_schema(engine)
