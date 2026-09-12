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
