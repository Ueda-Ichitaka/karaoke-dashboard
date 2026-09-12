"""Tests for admin actions on song requests: deleting an entry, scanning
whether a request already matches something in the library (exact folder
name, or just matching UltraStar metadata in an oddly-named folder), and
editing a request's fields (needed so an admin can point lyrics_url at a
filesystem path once they've prepared a lyrics file).
"""

from __future__ import annotations

from app.database import SessionLocal
from app.models import SongRequest


def _insert_request(band: str, song: str, **kwargs) -> int:
    with SessionLocal() as db:
        req = SongRequest(band_name=band, song_name=song, requester_username="admin", **kwargs)
        db.add(req)
        db.commit()
        db.refresh(req)
        return req.id


# --------------------------------------------------------------------- scan
def test_requests_view_flags_exact_folder_match(admin_client):
    _insert_request("Queen", "Bohemian Rhapsody")
    r = admin_client.get("/admin/requests")
    assert r.status_code == 200
    assert "In library" in r.text
    assert "Queen - Bohemian Rhapsody" in r.text


def test_requests_view_flags_metadata_only_match(admin_client):
    # "Testband - Multi Song" holds a song titled "Song A" - the folder name
    # itself doesn't follow "band - song", only the UltraStar tags match.
    _insert_request("Testband", "Song A")
    r = admin_client.get("/admin/requests")
    assert "Possibly added" in r.text
    assert "Testband - Multi Song" in r.text


def test_requests_view_no_match_shows_no_badge(admin_client):
    _insert_request("Nope", "Nope")
    r = admin_client.get("/admin/requests")
    assert "In library" not in r.text
    assert "Possibly added" not in r.text


# ------------------------------------------------------------------- delete
def test_delete_request_removes_it(admin_client):
    rid = _insert_request("Nope", "Nope")
    r = admin_client.post(f"/admin/requests/{rid}/delete", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/admin/requests"

    listing = admin_client.get("/admin/requests?show=all")
    assert "Nope" not in listing.text


def test_delete_unknown_request_is_404(admin_client):
    assert admin_client.post("/admin/requests/99999/delete").status_code == 404


# --------------------------------------------------------------------- edit
def test_edit_form_shows_current_values(admin_client):
    rid = _insert_request(
        "Journey", "Faithfully",
        youtube_url="https://youtu.be/abc", language="en",
        musicbrainz_id="mbid-1", lyrics_url="/songs/x.txt",
    )
    r = admin_client.get(f"/admin/requests/{rid}/edit")
    assert r.status_code == 200
    assert 'value="Journey"' in r.text
    assert 'value="Faithfully"' in r.text
    assert 'value="https://youtu.be/abc"' in r.text
    assert 'value="mbid-1"' in r.text
    assert 'value="/songs/x.txt"' in r.text
    assert '<option value="en" selected>' in r.text


def test_edit_saves_changes(admin_client):
    rid = _insert_request("Journey", "Faithfully")
    r = admin_client.post(
        f"/admin/requests/{rid}/edit",
        data={
            "band_name": "Journey", "song_name": "Faithfully",
            "youtube_url": "", "language": "en", "musicbrainz_id": "mbid-9",
            "lyrics_url": "/songs/Journey - Faithfully/lyrics.txt",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/admin/requests"

    r2 = admin_client.get(f"/admin/requests/{rid}/edit")
    assert 'value="mbid-9"' in r2.text
    assert 'value="/songs/Journey - Faithfully/lyrics.txt"' in r2.text


def test_edit_rejects_invalid_language(admin_client):
    rid = _insert_request("Journey", "Faithfully")
    r = admin_client.post(
        f"/admin/requests/{rid}/edit",
        data={"band_name": "Journey", "song_name": "Faithfully", "language": "zz"},
    )
    assert r.status_code == 422


def test_edit_requires_band_and_song(admin_client):
    rid = _insert_request("Journey", "Faithfully")
    r = admin_client.post(
        f"/admin/requests/{rid}/edit",
        data={"band_name": "", "song_name": ""},
    )
    assert r.status_code == 422


def test_edit_unknown_request_is_404(admin_client):
    assert admin_client.get("/admin/requests/99999/edit").status_code == 404


# ------------------------------------------------------------------- access
def test_non_admin_blocked_from_request_admin_actions(admin_client):
    rid = _insert_request("Journey", "Faithfully")
    admin_client.post("/admin/users", data={"username": "carol2", "password": "carolcarol"})
    admin_client.post("/logout")
    admin_client.post(
        "/login", data={"username": "carol2", "password": "carolcarol"}, follow_redirects=False
    )

    assert admin_client.get(f"/admin/requests/{rid}/edit").status_code == 403
    assert admin_client.post(
        f"/admin/requests/{rid}/edit", data={"band_name": "x", "song_name": "y"}
    ).status_code == 403
    assert admin_client.post(f"/admin/requests/{rid}/delete").status_code == 403
