"""Test fixtures.

Environment is configured at import time (before ``app`` is imported) so the
module-level settings/engine pick it up. The database is recreated per test.
"""

from __future__ import annotations

import os
import tempfile
import wave
from pathlib import Path

import pytest


def _write_silent_wav(path: Path, seconds: float, framerate: int = 100) -> None:
    """A minimal, valid audio file of an exact known duration, for fixtures."""
    n_frames = round(seconds * framerate)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(framerate)
        w.writeframes(b"\x00" * n_frames)

# --- configure environment before importing the app -------------------------
_TMP = Path(tempfile.mkdtemp(prefix="karaoke-test-"))
_SONGS_DIR = _TMP / "songs"
SONGS_DIR = _SONGS_DIR  # public alias for tests that need real fixture files
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

# A folder with one valid UltraStar song, complete with a cover image and a
# playable audio file (its duration is the song's displayed length).
_SOLO_DIR = _SONGS_DIR / "Testband - Solo Song"
_SOLO_DIR.mkdir(exist_ok=True)
(_SOLO_DIR / "Solo Song.txt").write_text(
    "#TITLE:Solo Song\n"
    "#ARTIST:Testband\n"
    "#GENRE:Rock\n"
    "#YEAR:1999\n"
    "#LANGUAGE:English\n"
    "#COVER:cover.jpg\n"
    "#MP3:song.wav\n"
    "#BPM:200\n"
    "#GAP:1000\n"
    ": 0 4 0 La\n"
    "E\n",
    encoding="utf-8",
)
(_SOLO_DIR / "cover.jpg").write_bytes(b"\xff\xd8\xff\xe0fakejpegbytes")
_write_silent_wav(_SOLO_DIR / "song.wav", seconds=180)

# A folder with two distinct UltraStar songs (a batch-import folder).
_MULTI_DIR = _SONGS_DIR / "Testband - Multi Song"
_MULTI_DIR.mkdir(exist_ok=True)
(_MULTI_DIR / "SongA.txt").write_text(
    "#TITLE:Song A\n#ARTIST:Testband\n#BPM:120\n#GAP:0\nE\n", encoding="utf-8"
)
(_MULTI_DIR / "SongB.txt").write_text(
    "#TITLE:Song B\n#ARTIST:Testband\n#BPM:140\n#GAP:0\nE\n", encoding="utf-8"
)

# A folder with a duet, tagged the UltraStar way.
_DUET_DIR = _SONGS_DIR / "Testband - Duet Song"
_DUET_DIR.mkdir(exist_ok=True)
(_DUET_DIR / "Duet Song.txt").write_text(
    "#TITLE:Duet Song\n"
    "#ARTIST:Testband\n"
    "#DUETSINGERP1:Alice\n"
    "#DUETSINGERP2:Bob\n"
    "#BPM:100\n"
    "#GAP:0\n"
    "E\n",
    encoding="utf-8",
)

# A folder produced by another library-management tool: nested subfolders
# instead of the flat "Artist - Title" convention - the integrity view's
# structure check must flag this.
_NESTED_DIR = _SONGS_DIR / "Coverband - Import Batch"
_NESTED_DIR.mkdir(exist_ok=True)
(_NESTED_DIR / "CD1").mkdir(exist_ok=True)
(_NESTED_DIR / "CD1" / "Track.txt").write_text(
    "#TITLE:Track\n#ARTIST:Coverband\n#BPM:120\n#GAP:0\nE\n", encoding="utf-8"
)

# A folder whose name matches one of its songs, but which also holds an
# unrelated song's files (e.g. from a batch-import bug) - the integrity
# view's misplaced-songs check must flag only the unrelated one.
_MISPLACED_DIR = _SONGS_DIR / "30 Seconds to Mars - Attack"
_MISPLACED_DIR.mkdir(exist_ok=True)
(_MISPLACED_DIR / "Attack.txt").write_text(
    "#TITLE:Attack\n#ARTIST:30 Seconds to Mars\n#BPM:140\n#GAP:0\nE\n", encoding="utf-8"
)
(_MISPLACED_DIR / "TheKill.txt").write_text(
    "#TITLE:The Kill\n#ARTIST:30 Seconds to Mars\n#BPM:150\n#GAP:0\nE\n", encoding="utf-8"
)

# A stray, non-UltraStar .txt file (e.g. a readme) that must not be mistaken
# for a song version: it lacks the mandatory BPM/GAP tags.
_JUNK_DIR = _SONGS_DIR / "Testband - Junk Text"
_JUNK_DIR.mkdir(exist_ok=True)
(_JUNK_DIR / "readme.txt").write_text("just some notes, not a song file\n", encoding="utf-8")

# Two folders holding the same song (same artist/title, different folders) -
# a genuine accidental duplicate, with a differing genre tag to exercise the
# per-field diff.
_DUP_A_DIR = _SONGS_DIR / "Coverband - Copycat Song"
_DUP_A_DIR.mkdir(exist_ok=True)
(_DUP_A_DIR / "Copycat Song.txt").write_text(
    "#TITLE:Copycat Song\n#ARTIST:Coverband\n#GENRE:Rock\n#BPM:130\n#GAP:0\nE\n",
    encoding="utf-8",
)
_DUP_B_DIR = _SONGS_DIR / "Coverband - Copycat Song (Reupload)"
_DUP_B_DIR.mkdir(exist_ok=True)
(_DUP_B_DIR / "Copycat Song.txt").write_text(
    "#TITLE:  copycat song  \n#ARTIST:Coverband\n#GENRE:Pop\n#BPM:130\n#GAP:0\nE\n",
    encoding="utf-8",
)

# A duet arrangement of that same song. It must NOT be grouped with the two
# solo copies above - duet vs. solo is an intentional variant, not a dupe.
_DUP_DUET_DIR = _SONGS_DIR / "Coverband - Copycat Song (Duet)"
_DUP_DUET_DIR.mkdir(exist_ok=True)
(_DUP_DUET_DIR / "Copycat Song.txt").write_text(
    "#TITLE:Copycat Song\n#ARTIST:Coverband\n#DUETSINGERP1:Alice\n#DUETSINGERP2:Bob\n"
    "#BPM:130\n#GAP:0\nE\n",
    encoding="utf-8",
)

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
