"""Tests for app/pending_migration.py: when the pending-review workflow
first ships, any request/report that was already status="open" (submitted
before admin review existed) is retroactively moved into the new pending
table, so an admin has to review it like any other new submission before
it's exportable again. A "done"/"resolved" row is left alone - it's already
finished, not a reason to re-review it.
"""

from __future__ import annotations

from app.database import SessionLocal
from app.models import BrokenReport, PendingBrokenReport, PendingSongRequest, SongRequest
from app.pending_migration import migrate_open_rows_to_pending


def test_moves_an_open_song_request_into_pending(fresh_db):
    with SessionLocal() as db:
        db.add(
            SongRequest(
                band_name="Journey", song_name="Faithfully", status="open",
                requester_username="admin",
            )
        )
        db.commit()

        migrate_open_rows_to_pending(db)
        db.commit()

        assert db.query(SongRequest).count() == 0
        pending = db.query(PendingSongRequest).one()
        assert pending.band_name == "Journey"
        assert pending.song_name == "Faithfully"


def test_leaves_a_done_song_request_alone(fresh_db):
    with SessionLocal() as db:
        db.add(
            SongRequest(
                band_name="Journey", song_name="Faithfully", status="done",
                requester_username="admin",
            )
        )
        db.commit()

        migrate_open_rows_to_pending(db)
        db.commit()

        assert db.query(SongRequest).count() == 1
        assert db.query(PendingSongRequest).count() == 0


def test_moves_an_open_broken_report_into_pending(fresh_db):
    with SessionLocal() as db:
        db.add(
            BrokenReport(
                song_folder="Queen - Bohemian Rhapsody", category="audio",
                description="no audio", status="open", reporter_username="admin",
            )
        )
        db.commit()

        migrate_open_rows_to_pending(db)
        db.commit()

        assert db.query(BrokenReport).count() == 0
        pending = db.query(PendingBrokenReport).one()
        assert pending.song_folder == "Queen - Bohemian Rhapsody"
        assert pending.description == "no audio"


def test_leaves_a_resolved_broken_report_alone(fresh_db):
    with SessionLocal() as db:
        db.add(
            BrokenReport(
                song_folder="Queen - Bohemian Rhapsody", category="audio",
                description="no audio", status="resolved", reporter_username="admin",
            )
        )
        db.commit()

        migrate_open_rows_to_pending(db)
        db.commit()

        assert db.query(BrokenReport).count() == 1
        assert db.query(PendingBrokenReport).count() == 0


def test_is_idempotent(fresh_db):
    with SessionLocal() as db:
        db.add(
            SongRequest(
                band_name="Journey", song_name="Faithfully", status="open",
                requester_username="admin",
            )
        )
        db.commit()

        migrate_open_rows_to_pending(db)
        db.commit()
        migrate_open_rows_to_pending(db)  # must not raise, must not duplicate
        db.commit()

        assert db.query(PendingSongRequest).count() == 1
