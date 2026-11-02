"""Tests for the "Resolved" button in the Reported page's Needs review table
(POST /admin/reports/pending/{id}/resolve): the report moves to the
admitted list as resolved in one step - without Admit's required-field
checks, keeping the time it was submitted - so it stays in the history and
can be reopened, and a new report for the song is a new occurrence.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from app.database import SessionLocal
from app.models import BrokenReport, PendingBrokenReport

FOLDER = "Queen - Bohemian Rhapsody"
REPORTED = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def _pending(**fields) -> int:
    values = {"song_folder": FOLDER, "category": "audio", "description": "crackles", "reporter_username": "admin",
              "created_at": REPORTED}
    values.update(fields)
    with SessionLocal() as db:
        row = PendingBrokenReport(**values)
        db.add(row)
        db.commit()
        return row.id


def test_resolving_moves_the_report_to_the_admitted_list_as_resolved(admin_client):
    pending_id = _pending(language="en", genius_url="https://genius.com/Queen-bohemian-rhapsody-lyrics",
                          cover_url="https://example.com/c.jpg", genre="rock", trait="choir")
    r = admin_client.post(f"/admin/reports/pending/{pending_id}/resolve", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/admin/reports"
    with SessionLocal() as db:
        assert db.query(PendingBrokenReport).count() == 0
        report = db.query(BrokenReport).one()
    assert report.status == "resolved"
    assert (report.song_folder, report.category, report.description, report.language, report.genius_url,
            report.cover_url, report.genre, report.trait, report.reporter_username) == (
        FOLDER, "audio", "crackles", "en", "https://genius.com/Queen-bohemian-rhapsody-lyrics",
        "https://example.com/c.jpg", "rock", "choir", "admin")
    assert report.created_at.replace(tzinfo=report.created_at.tzinfo or UTC) == REPORTED


def test_an_incomplete_report_can_be_resolved(admin_client):
    pending_id = _pending(category="lyrics", description="", language=None, genius_url=None)
    admin_client.post(f"/admin/reports/pending/{pending_id}/resolve")
    with SessionLocal() as db:
        assert db.query(BrokenReport).one().status == "resolved"


def test_needs_review_has_a_resolved_button(admin_client):
    pending_id = _pending()
    html = admin_client.get("/admin/reports").text
    form = re.search(rf'<form method="post" action="/admin/reports/pending/{pending_id}/resolve".*?</form>',
                     html, re.S)
    assert form is not None
    assert 'name="csrf_token"' in form.group(0)
    assert ">Resolved</button>" in form.group(0)


def test_a_resolved_report_shows_under_all_not_open(admin_client):
    admin_client.post(f"/admin/reports/pending/{_pending()}/resolve")
    assert f'<span class="mono">{FOLDER}</span>' not in admin_client.get("/admin/reports?show=open").text
    html = admin_client.get("/admin/reports?show=all").text
    assert f'<span class="mono">{FOLDER}</span>' in html
    assert "0 open" in html


def test_a_new_report_for_the_song_is_a_new_occurrence(admin_client):
    admin_client.post(f"/admin/reports/pending/{_pending()}/resolve")
    admin_client.post("/report", data={"song_folder": FOLDER, "category": "audio", "description": "again",
                                       "language": "en"})
    with SessionLocal() as db:
        assert db.query(PendingBrokenReport).one().description == "again"


def test_an_unknown_report_is_a_404(admin_client):
    assert admin_client.post("/admin/reports/pending/999/resolve").status_code == 404


def test_only_admins_can_resolve(client):
    pending_id = _pending()
    r = client.post(f"/admin/reports/pending/{pending_id}/resolve", follow_redirects=False)
    assert r.status_code in (303, 403)
    with SessionLocal() as db:
        assert db.query(PendingBrokenReport).count() == 1
