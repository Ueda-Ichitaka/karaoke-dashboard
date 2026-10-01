"""Tests for the admin "pending review" section on /admin/requests: a newly
submitted request now lands in PendingSongRequest, shown in a section above
the existing admitted-list table. An admin can edit it in place, admit it
(moved into SongRequest once it passes the strict-profile completeness
check, app/profiles.py), or discard it outright.
"""

from __future__ import annotations

from app.database import SessionLocal
from app.models import PendingSongRequest, SongRequest


def _submit(admin_client, **overrides):
    data = {"band_name": "Journey", "song_name": "Faithfully"}
    data.update(overrides)
    admin_client.post("/request", data=data)


def _pending_id() -> int:
    with SessionLocal() as db:
        row = db.query(PendingSongRequest).one()
        return row.id


def test_pending_section_shown_on_admin_requests_page(admin_client):
    _submit(admin_client)
    r = admin_client.get("/admin/requests")
    assert r.status_code == 200
    assert "Faithfully" in r.text
    assert "Needs review" in r.text


def test_pending_entry_not_in_the_admitted_table_or_csv(admin_client):
    _submit(admin_client)
    r = admin_client.get("/admin/requests.csv", params={"scope": "all"})
    assert "Faithfully" not in r.text


def test_edit_pending_request_saves_changes(admin_client):
    _submit(admin_client)
    pid = _pending_id()
    r = admin_client.get(f"/admin/requests/pending/{pid}/edit")
    assert r.status_code == 200
    assert 'value="Faithfully"' in r.text

    r = admin_client.post(
        f"/admin/requests/pending/{pid}/edit",
        data={"band_name": "Journey", "song_name": "Faithfully (Live)"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    with SessionLocal() as db:
        row = db.get(PendingSongRequest, pid)
        assert row.song_name == "Faithfully (Live)"


def test_admit_blocked_until_strict_fields_are_filled_in(admin_client):
    _submit(admin_client)  # karaoke-night default: only band/song present
    pid = _pending_id()

    r = admin_client.post(f"/admin/requests/pending/{pid}/admit")
    assert r.status_code == 422
    assert "youtube" in r.text.lower()
    assert "language" in r.text.lower()
    assert "lyrics" in r.text.lower()

    with SessionLocal() as db:
        assert db.query(PendingSongRequest).count() == 1
        assert db.query(SongRequest).count() == 0


def test_admit_succeeds_once_complete_and_moves_the_row(admin_client):
    _submit(admin_client)
    pid = _pending_id()
    admin_client.post(
        f"/admin/requests/pending/{pid}/edit",
        data={
            "band_name": "Journey", "song_name": "Faithfully",
            "youtube_url": "https://www.youtube.com/watch?v=x",
            "language": "en", "lyrics_url": "https://genius.com/journey-faithfully-lyrics",
        },
    )

    r = admin_client.post(f"/admin/requests/pending/{pid}/admit", follow_redirects=False)
    assert r.status_code == 303

    with SessionLocal() as db:
        assert db.query(PendingSongRequest).count() == 0
        admitted = db.query(SongRequest).one()
        assert admitted.song_name == "Faithfully"
        assert admitted.status == "open"

    listing = admin_client.get("/admin/requests?show=all")
    assert "Faithfully" in listing.text


def test_discard_deletes_the_pending_entry(admin_client):
    _submit(admin_client)
    pid = _pending_id()
    r = admin_client.post(f"/admin/requests/pending/{pid}/discard", follow_redirects=False)
    assert r.status_code == 303
    with SessionLocal() as db:
        assert db.query(PendingSongRequest).count() == 0


def test_pending_duplicate_check_still_blocks_a_second_karaoke_night_submission(admin_client):
    _submit(admin_client)
    r = admin_client.post("/request", data={"band_name": "Journey", "song_name": "Faithfully"})
    assert r.status_code == 422
    assert "already" in r.text.lower()


def test_pending_discard_button_present_in_listing(admin_client):
    _submit(admin_client)
    pid = _pending_id()
    r = admin_client.get("/admin/requests")
    assert f"/admin/requests/pending/{pid}/discard" in r.text
    assert f"/admin/requests/pending/{pid}/admit" in r.text
    assert f"/admin/requests/pending/{pid}/edit" in r.text
