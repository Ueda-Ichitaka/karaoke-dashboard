"""Test fixtures.

Environment is configured at import time (before ``app`` is imported) so the
module-level settings/engine pick it up. The database is recreated per test.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# --- configure environment before importing the app -------------------------
_TMP = Path(tempfile.mkdtemp(prefix="karaoke-test-"))
_SONGS_DIR = _TMP / "songs"
_SONGS_DIR.mkdir(parents=True, exist_ok=True)
for _name in [
    "Queen - Bohemian Rhapsody",
    "a-ha - Take On Me",
    "ABBA - Dancing Queen",
    "Toto - Africa",
    "PlainFolderNoSeparator",
]:
    (_SONGS_DIR / _name).mkdir(exist_ok=True)
(_SONGS_DIR / "@eaDir").mkdir(exist_ok=True)
(_SONGS_DIR / ".hidden").mkdir(exist_ok=True)

os.environ.update(
    DATABASE_URL=f"sqlite:///{_TMP / 'test.db'}",
    SECRET_KEY="test-secret",
    SESSION_COOKIE_SECURE="false",
    SONGS_DIR=str(_SONGS_DIR),
    SCAN_CACHE_SECONDS="0",
    ADMIN_USERNAME="admin",
    ADMIN_PASSWORD="adminadmin",
)

from app.database import Base, SessionLocal, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.security import seed_admin  # noqa: E402


@pytest.fixture()
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    init_db()
    with SessionLocal() as db:
        seed_admin(db)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(fresh_db):
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def admin_client(client):
    resp = client.post(
        "/login",
        data={"username": "admin", "password": "adminadmin"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    return client
