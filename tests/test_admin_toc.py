"""Tests for the slim fixed table-of-contents sidebar shown on admin pages
that have more than one section (app/templates/base.html's toc block), so
an admin can jump to a section instead of scrolling - see
app/templates/admin/integrity.html, duplicates.html, requests.html, reports.html.
"""

from __future__ import annotations

from app.database import SessionLocal
from app.models import PendingBrokenReport, PendingSongRequest


def test_integrity_view_has_a_toc_with_its_three_sections(admin_client):
    r = admin_client.get("/admin/integrity")
    assert r.status_code == 200
    assert 'class="toc"' in r.text
    assert 'href="#format"' in r.text
    assert 'href="#structure"' in r.text
    assert 'href="#misplaced"' in r.text


def test_requests_view_has_no_toc_without_pending_entries(admin_client):
    r = admin_client.get("/admin/requests")
    assert 'class="toc"' not in r.text


def test_requests_view_has_a_toc_once_something_is_pending(admin_client):
    with SessionLocal() as db:
        db.add(PendingSongRequest(band_name="Journey", song_name="Faithfully", requester_username="admin"))
        db.commit()
    r = admin_client.get("/admin/requests")
    assert 'class="toc"' in r.text
    assert 'href="#needs-review"' in r.text
    assert 'href="#all-requests"' in r.text


def test_reports_view_has_a_toc_once_something_is_pending(admin_client):
    with SessionLocal() as db:
        db.add(
            PendingBrokenReport(
                song_folder="Queen - Bohemian Rhapsody", category="audio",
                description="no audio", reporter_username="admin",
            )
        )
        db.commit()
    r = admin_client.get("/admin/reports")
    assert 'class="toc"' in r.text
    assert 'href="#needs-review"' in r.text
    assert 'href="#all-reports"' in r.text
