"""Tests for the admin edit view on broken-song reports (mirrors the
song-request edit view - see tests/test_admin_requests.py).
"""

from __future__ import annotations

from app.database import SessionLocal
from app.models import BrokenReport


def _insert_report(song_folder="Queen - Bohemian Rhapsody", **kwargs) -> int:
    kwargs.setdefault("category", "audio")
    kwargs.setdefault("description", "cuts out")
    kwargs.setdefault("language", "de")
    with SessionLocal() as db:
        r = BrokenReport(song_folder=song_folder, reporter_username="admin", **kwargs)
        db.add(r)
        db.commit()
        db.refresh(r)
        return r.id


def test_admin_reports_view_has_an_edit_link(admin_client):
    _insert_report()
    r = admin_client.get("/admin/reports")
    assert "/admin/reports/1/edit" in r.text


def test_edit_form_shows_current_values(admin_client):
    rid = _insert_report(
        genius_url="https://genius.com/x-lyrics", cover_url="https://example.com/cover.jpg"
    )
    r = admin_client.get(f"/admin/reports/{rid}/edit")
    assert r.status_code == 200
    assert "Queen - Bohemian Rhapsody" in r.text
    assert "cuts out" in r.text
    assert 'value="https://genius.com/x-lyrics"' in r.text
    assert 'value="https://example.com/cover.jpg"' in r.text
    assert '<option value="de" selected>' in r.text
    assert '<option value="audio" selected>' in r.text


def test_edit_saves_changes(admin_client):
    rid = _insert_report()
    r = admin_client.post(
        f"/admin/reports/{rid}/edit",
        data={
            "song_folder": "Queen - Bohemian Rhapsody", "category": "video",
            "description": "no video at all", "language": "en",
            "cover_url": "https://example.com/new.jpg",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/admin/reports"

    r2 = admin_client.get(f"/admin/reports/{rid}/edit")
    assert "no video at all" in r2.text
    assert 'value="https://example.com/new.jpg"' in r2.text
    assert '<option value="video" selected>' in r2.text
    assert '<option value="en" selected>' in r2.text


def test_edit_requires_category_and_language(admin_client):
    rid = _insert_report()
    r = admin_client.post(
        f"/admin/reports/{rid}/edit",
        data={"song_folder": "Queen - Bohemian Rhapsody", "category": "", "language": ""},
    )
    assert r.status_code == 422


def test_edit_requires_genius_link_for_lyrics_category(admin_client):
    rid = _insert_report()
    r = admin_client.post(
        f"/admin/reports/{rid}/edit",
        data={
            "song_folder": "Queen - Bohemian Rhapsody", "category": "lyrics",
            "description": "", "language": "de",
        },
    )
    assert r.status_code == 422
    assert "genius" in r.text.lower()


def test_edit_rejects_unknown_song(admin_client):
    rid = _insert_report()
    r = admin_client.post(
        f"/admin/reports/{rid}/edit",
        data={"song_folder": "Nope - Nope", "category": "audio", "language": "de"},
    )
    assert r.status_code == 422


def test_edit_unknown_report_is_404(admin_client):
    assert admin_client.get("/admin/reports/99999/edit").status_code == 404
    assert admin_client.post(
        "/admin/reports/99999/edit",
        data={"song_folder": "Queen - Bohemian Rhapsody", "category": "audio", "language": "de"},
    ).status_code == 404


def test_non_admin_blocked_from_report_edit(admin_client):
    rid = _insert_report()
    admin_client.post("/admin/users", data={"username": "dana", "password": "danadanadana"})
    admin_client.post("/logout")
    admin_client.post("/login", data={"username": "dana", "password": "danadanadana"}, follow_redirects=False)

    assert admin_client.get(f"/admin/reports/{rid}/edit").status_code == 403
    assert admin_client.post(
        f"/admin/reports/{rid}/edit",
        data={"song_folder": "Queen - Bohemian Rhapsody", "category": "audio", "language": "de"},
    ).status_code == 403
