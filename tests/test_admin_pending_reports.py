"""Tests for the admin "pending review" section on /admin/reports: a newly
submitted report now lands in PendingBrokenReport, shown in a section above
the existing admitted-list table. An admin can edit it in place, admit it
(moved into BrokenReport once it passes the strict-profile completeness
check, app/profiles.py), or discard it outright.
"""

from __future__ import annotations

from app.database import SessionLocal
from app.models import BrokenReport, PendingBrokenReport


def _submit(admin_client, **overrides):
    data = {
        "song_folder": "Queen - Bohemian Rhapsody", "category": "audio",
        "description": "cuts out at the start", "language": "en",
    }
    data.update(overrides)
    admin_client.post("/report", data=data)


def _set_report_profile_karaoke_night(admin_client) -> None:
    admin_client.post(
        "/admin/settings", data={"request_profile": "karaoke_night", "report_profile": "karaoke_night"}
    )


def _pending_id() -> int:
    with SessionLocal() as db:
        row = db.query(PendingBrokenReport).one()
        return row.id


def test_pending_section_shown_on_admin_reports_page(admin_client):
    _submit(admin_client)
    r = admin_client.get("/admin/reports")
    assert r.status_code == 200
    assert "cuts out at the start" in r.text
    assert "Needs review" in r.text


def test_pending_entry_not_in_the_admitted_table_or_csv(admin_client):
    _submit(admin_client)
    r = admin_client.get("/admin/reports.csv", params={"scope": "all"})
    assert "cuts out at the start" not in r.text


def test_edit_pending_report_saves_changes(admin_client):
    _submit(admin_client)
    pid = _pending_id()
    r = admin_client.get(f"/admin/reports/pending/{pid}/edit")
    assert r.status_code == 200
    assert "cuts out at the start" in r.text

    r = admin_client.post(
        f"/admin/reports/pending/{pid}/edit",
        data={
            "song_folder": "Queen - Bohemian Rhapsody", "category": "audio",
            "description": "cuts out completely",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    with SessionLocal() as db:
        row = db.get(PendingBrokenReport, pid)
        assert row.description == "cuts out completely"


def test_admit_blocked_until_strict_language_is_filled_in(admin_client):
    _set_report_profile_karaoke_night(admin_client)
    _submit(admin_client, language="")  # allowed through under karaoke-night
    pid = _pending_id()

    r = admin_client.post(f"/admin/reports/pending/{pid}/admit")
    assert r.status_code == 422
    assert "language" in r.text.lower()

    with SessionLocal() as db:
        assert db.query(PendingBrokenReport).count() == 1
        assert db.query(BrokenReport).count() == 0


def test_admit_succeeds_once_complete_and_moves_the_row(admin_client):
    _submit(admin_client)
    pid = _pending_id()
    admin_client.post(
        f"/admin/reports/pending/{pid}/edit",
        data={
            "song_folder": "Queen - Bohemian Rhapsody", "category": "audio",
            "description": "cuts out at the start", "language": "en",
        },
    )

    r = admin_client.post(f"/admin/reports/pending/{pid}/admit", follow_redirects=False)
    assert r.status_code == 303

    with SessionLocal() as db:
        assert db.query(PendingBrokenReport).count() == 0
        admitted = db.query(BrokenReport).one()
        assert admitted.description == "cuts out at the start"
        assert admitted.status == "open"
        # song_artist/song_title are re-derived from song_folder on admit
        assert admitted.song_artist == "Queen"
        assert admitted.song_title == "Bohemian Rhapsody"

    listing = admin_client.get("/admin/reports?show=all")
    assert "cuts out at the start" in listing.text


def test_admit_blocked_requires_genius_link_for_lyrics_category(admin_client):
    _set_report_profile_karaoke_night(admin_client)
    _submit(admin_client, category="lyrics", language="de")
    pid = _pending_id()

    r = admin_client.post(f"/admin/reports/pending/{pid}/admit")
    assert r.status_code == 422
    assert "genius" in r.text.lower()


def test_discard_deletes_the_pending_entry(admin_client):
    _submit(admin_client)
    pid = _pending_id()
    r = admin_client.post(f"/admin/reports/pending/{pid}/discard", follow_redirects=False)
    assert r.status_code == 303
    with SessionLocal() as db:
        assert db.query(PendingBrokenReport).count() == 0


def test_pending_action_links_present_in_listing(admin_client):
    _submit(admin_client)
    pid = _pending_id()
    r = admin_client.get("/admin/reports")
    assert f"/admin/reports/pending/{pid}/discard" in r.text
    assert f"/admin/reports/pending/{pid}/admit" in r.text
    assert f"/admin/reports/pending/{pid}/edit" in r.text
