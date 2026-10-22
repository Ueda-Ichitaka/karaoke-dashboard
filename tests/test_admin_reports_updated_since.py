"""Tests for the "Updated since report" mark in the admitted reports table on
/admin/reports: a report is marked when the library scan recorded a write to
its song's files (LibraryFolder.last_write_at or a detected change,
updated_at - app/library_history.py) after the report was drafted - so an
admin can check the fix and resolve it. That includes a fix written before
the library scan's first run. Admitting keeps the time the report was
drafted, which is what counts.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from app.database import SessionLocal
from app.models import BrokenReport, LibraryFolder, PendingBrokenReport

FOLDER = "Queen - Bohemian Rhapsody"
REPORTED = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
MARK = "Updated since report"


def _report(created_at: datetime = REPORTED, folder: str = FOLDER) -> None:
    with SessionLocal() as db:
        db.add(BrokenReport(song_folder=folder, category="audio", description="x", reporter_username="admin",
                            created_at=created_at))
        db.commit()


def _updated(at: datetime | None, folder: str = FOLDER) -> None:
    with SessionLocal() as db:
        db.add(LibraryFolder(folder=folder, first_seen_at=None, follows_convention=True, files="{}",
                             updated_at=at))
        db.commit()


def _row(html: str, folder: str = FOLDER) -> str:
    rows = [row for row in re.findall(r"<tr.*?</tr>", html, re.S) if f'<span class="mono">{folder}</span>' in row]
    assert len(rows) == 1
    return rows[0]


def test_a_song_written_after_its_report_is_marked(admin_client):
    _report()
    _updated(datetime(2026, 10, 5, 9, 30, tzinfo=UTC))
    row = _row(admin_client.get("/admin/reports").text)
    assert MARK in row
    assert 'title="Song files written 2026-10-05 09:30"' in row


def test_a_song_written_before_its_report_is_not_marked(admin_client):
    _report()
    _updated(datetime(2026, 9, 30, tzinfo=UTC))
    assert MARK not in _row(admin_client.get("/admin/reports").text)


def test_a_song_without_a_recorded_update_is_not_marked(admin_client):
    _report()
    _report(folder="Toto - Africa")
    _updated(None)
    html = admin_client.get("/admin/reports").text
    assert MARK not in _row(html)
    assert MARK not in _row(html, "Toto - Africa")


def test_the_admitted_table_has_the_column(admin_client):
    _report()
    assert "<th>Song files</th>" in admin_client.get("/admin/reports").text


def test_needs_review_shows_no_mark(admin_client):
    with SessionLocal() as db:
        db.add(PendingBrokenReport(song_folder=FOLDER, category="audio", description="x",
                                   reporter_username="admin", created_at=REPORTED))
        db.commit()
    _updated(datetime(2026, 10, 5, tzinfo=UTC))
    assert MARK not in admin_client.get("/admin/reports").text


def test_admitting_keeps_the_time_the_report_was_drafted(admin_client):
    with SessionLocal() as db:
        db.add(PendingBrokenReport(song_folder=FOLDER, category="audio", description="x", language="en",
                                   genius_url="https://genius.com/Queen-bohemian-rhapsody-lyrics",
                                   reporter_username="admin", created_at=REPORTED))
        db.commit()
        pending_id = db.query(PendingBrokenReport).one().id
    admin_client.post(f"/admin/reports/pending/{pending_id}/admit")
    with SessionLocal() as db:
        admitted = db.query(BrokenReport).one().created_at
    assert admitted.replace(tzinfo=admitted.tzinfo or UTC) == REPORTED


def test_a_fix_written_before_the_first_scan_is_marked(admin_client):
    _report()
    with SessionLocal() as db:
        db.add(LibraryFolder(folder=FOLDER, first_seen_at=None, follows_convention=True, files="{}",
                             last_write_at=datetime(2026, 10, 3, 8, 0, tzinfo=UTC), updated_at=None))
        db.commit()
    row = _row(admin_client.get("/admin/reports").text)
    assert MARK in row
    assert 'title="Song files written 2026-10-03 08:00"' in row
