"""Tests for app/known_broken.py: which library folders are currently known
to be broken - a report still awaiting review (PendingBrokenReport) or an
admitted one still open (BrokenReport). A resolved report no longer counts,
and in the "until updated" badge mode neither does a report the song's
files were written after (LibraryFolder.updated_at).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.database import SessionLocal
from app.known_broken import known_broken
from app.models import BrokenReport, LibraryFolder, PendingBrokenReport


def _pending(folder: str, category: str | None = "audio", **fields) -> PendingBrokenReport:
    return PendingBrokenReport(song_folder=folder, category=category, description="x", reporter_username="admin",
                               **fields)


def _admitted(folder: str, category: str | None = "audio", status: str = "open", **fields) -> BrokenReport:
    return BrokenReport(song_folder=folder, category=category, description="x", status=status,
                        reporter_username="admin", **fields)


def test_pending_and_open_reports_count_as_broken(fresh_db):
    with SessionLocal() as db:
        db.add_all([_pending("Queen - Bohemian Rhapsody", "lyrics"), _admitted("Toto - Africa", "gap")])
        db.commit()
        assert known_broken(db) == {
            "Queen - Bohemian Rhapsody": "Lyrics broken",
            "Toto - Africa": "#GAP (song starts too early/late)",
        }


def test_a_resolved_report_does_not_count(fresh_db):
    with SessionLocal() as db:
        db.add(_admitted("Toto - Africa", status="resolved"))
        db.commit()
        assert known_broken(db) == {}


def test_every_distinct_category_of_a_folder_is_listed_once(fresh_db):
    with SessionLocal() as db:
        db.add_all([
            _pending("Toto - Africa", "audio"),
            _admitted("Toto - Africa", "lyrics"),
            _admitted("Toto - Africa", "audio"),
        ])
        db.commit()
        assert known_broken(db) == {"Toto - Africa": "Missing audio, Lyrics broken"}


def test_a_report_without_category_still_counts(fresh_db):
    with SessionLocal() as db:
        db.add(_admitted("Toto - Africa", category=None))
        db.commit()
        assert known_broken(db) == {"Toto - Africa": ""}


# ---- "until updated" mode: a song-file write after a report outdates it ----
REPORTED = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def _updated(folder: str, at: datetime | None) -> LibraryFolder:
    return LibraryFolder(folder=folder, first_seen_at=None, follows_convention=True, files="{}", updated_at=at)


def test_until_updated_drops_a_report_the_song_was_updated_after(fresh_db):
    with SessionLocal() as db:
        db.add_all([
            _admitted("Toto - Africa", created_at=REPORTED), _updated("Toto - Africa", REPORTED + timedelta(days=4)),
            _pending("Queen - Bohemian Rhapsody", created_at=REPORTED),
            _updated("Queen - Bohemian Rhapsody", REPORTED + timedelta(hours=1)),
        ])
        db.commit()
        assert known_broken(db, until_updated=True) == {}
        assert set(known_broken(db)) == {"Toto - Africa", "Queen - Bohemian Rhapsody"}  # until resolved


def test_until_updated_keeps_a_report_newer_than_the_update(fresh_db):
    with SessionLocal() as db:
        db.add_all([
            _admitted("Toto - Africa", created_at=REPORTED), _updated("Toto - Africa", REPORTED - timedelta(days=1)),
            _admitted("ABBA - Dancing Queen", created_at=REPORTED), _updated("ABBA - Dancing Queen", None),
            _admitted("a-ha - Take On Me", created_at=REPORTED),
        ])
        db.commit()
        assert set(known_broken(db, until_updated=True)) == {"Toto - Africa", "ABBA - Dancing Queen",
                                                             "a-ha - Take On Me"}


def test_until_updated_lists_only_the_categories_reported_after_the_update(fresh_db):
    with SessionLocal() as db:
        db.add_all([
            _admitted("Toto - Africa", "audio", created_at=REPORTED),
            _pending("Toto - Africa", "lyrics", created_at=REPORTED + timedelta(days=9)),
            _updated("Toto - Africa", REPORTED + timedelta(days=4)),
        ])
        db.commit()
        assert known_broken(db, until_updated=True) == {"Toto - Africa": "Lyrics broken"}
