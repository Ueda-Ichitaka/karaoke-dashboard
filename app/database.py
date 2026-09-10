"""Database engine, session factory and startup helpers."""

from __future__ import annotations

import time
from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
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
    for attempt in range(1, retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except OperationalError as err:  # pragma: no cover - timing dependent
            last_err = err
            print(f"[startup] database not ready (attempt {attempt}/{retries}); retrying in {delay}s")
            time.sleep(delay)
    raise RuntimeError(f"database unreachable after {retries} attempts") from last_err


def init_db() -> None:
    """Create tables. For real migrations, swap this for Alembic."""
    from . import models  # noqa: F401  (register models on Base.metadata)

    Base.metadata.create_all(bind=engine)
