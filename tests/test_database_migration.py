"""Tests for the lightweight schema-sync helper that adds columns to
already-existing tables (app/database.py: _sync_schema), since create_all()
only creates missing tables and never alters existing ones.
"""

from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from app.database import _sync_schema


def test_sync_schema_adds_missing_nullable_columns(tmp_path):
    db_path = tmp_path / "old-shape.db"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE song_requests ("
                "id INTEGER PRIMARY KEY, band_name VARCHAR(512) NOT NULL, "
                "song_name VARCHAR(512) NOT NULL, youtube_url VARCHAR(1024), "
                "status VARCHAR(16) NOT NULL, requester_id INTEGER, "
                "requester_username VARCHAR(64) NOT NULL, created_at DATETIME NOT NULL)"
            )
        )

    _sync_schema(engine)

    columns = {c["name"] for c in inspect(engine).get_columns("song_requests")}
    assert {"language", "musicbrainz_id", "lyrics_url"} <= columns

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO song_requests "
                "(band_name, song_name, status, requester_username, created_at) "
                "VALUES ('Band', 'Song', 'open', 'tester', '2026-01-01')"
            )
        )
        row = conn.execute(
            text("SELECT language, musicbrainz_id, lyrics_url FROM song_requests")
        ).one()
    assert row == (None, None, None)


def test_sync_schema_is_a_noop_when_columns_already_present(tmp_path):
    db_path = tmp_path / "new-shape.db"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE song_requests ("
                "id INTEGER PRIMARY KEY, band_name VARCHAR(512) NOT NULL, "
                "song_name VARCHAR(512) NOT NULL, youtube_url VARCHAR(1024), "
                "status VARCHAR(16) NOT NULL, requester_id INTEGER, "
                "requester_username VARCHAR(64) NOT NULL, created_at DATETIME NOT NULL, "
                "language VARCHAR(8), musicbrainz_id VARCHAR(64), lyrics_url VARCHAR(1024))"
            )
        )

    _sync_schema(engine)  # must not raise on an already-current table

    columns = {c["name"] for c in inspect(engine).get_columns("song_requests")}
    assert {"language", "musicbrainz_id", "lyrics_url"} <= columns


def test_app_start_keeps_admitted_rows_admitted_and_tagged(fresh_db):
    # init_db() runs on every app start: it must never move an admitted row
    # back to Needs review or touch its genre/trait.
    from app.database import SessionLocal, init_db
    from app.models import BrokenReport, PendingBrokenReport, PendingSongRequest, SongRequest

    with SessionLocal() as db:
        db.add(SongRequest(band_name="Arkona", song_name="Goi", status="open", genre="metal,folk",
                           trait="harsh_vocals", requester_username="admin"))
        db.add(BrokenReport(song_folder="Queen - Bohemian Rhapsody", category="audio", description="cuts out",
                            status="open", genre="rock", trait="choir", reporter_username="admin"))
        db.commit()

    init_db()
    init_db()

    with SessionLocal() as db:
        assert db.query(PendingSongRequest).count() == 0
        assert db.query(PendingBrokenReport).count() == 0
        request = db.query(SongRequest).one()
        report = db.query(BrokenReport).one()
        assert (request.status, request.genre, request.trait) == ("open", "metal,folk", "harsh_vocals")
        assert (report.status, report.genre, report.trait) == ("open", "rock", "choir")
