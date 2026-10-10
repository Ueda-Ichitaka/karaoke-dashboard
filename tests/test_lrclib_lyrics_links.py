"""Tests for lrclib.net lyrics links (lrclib.net/tracks/<id>), which the song
factory reads besides genius.com song pages: every form with a lyrics link
field (public request/report, admin request/report edit) and the CSV import
accept one, and each field's tooltip names both sites.
"""

from __future__ import annotations

import re

from app.database import SessionLocal
from app.models import PendingBrokenReport, PendingSongRequest

_FOLDER = "Queen - Bohemian Rhapsody"
_LRCLIB = "https://lrclib.net/tracks/123456"
_TIP_RE = re.compile(r'data-tip="([^"]*)"')

_REQUEST_ADMIN_FIELDS = {
    "youtube_url": "https://www.youtube.com/watch?v=fJ9rUzIMcZQ",
    "language": "en",
    "musicbrainz_id": "b1a9c0e9-d987-4042-ae91-78d6a3267d69",
}


def _lyrics_tip(html: str) -> str:
    """The tooltip of the lyrics link field: the first data-tip naming a lyrics site."""
    return next(tip for tip in _TIP_RE.findall(html) if "genius.com" in tip)


def _pending_report_id(admin_client) -> int:
    admin_client.post(
        "/report",
        data={"song_folder": _FOLDER, "category": "audio", "description": "cuts out", "language": "en"},
    )
    with SessionLocal() as db:
        return db.query(PendingBrokenReport).one().id


def _pending_request_id(admin_client) -> int:
    admin_client.post("/request", data={"band_name": "Queen", "song_name": "Innuendo"})
    with SessionLocal() as db:
        return db.query(PendingSongRequest).one().id


# ------------------------------------------------------------------ tooltips
def test_public_request_tooltip_names_genius_and_lrclib(admin_client):
    tip = _lyrics_tip(admin_client.get("/request").text)
    assert "lrclib.net" in tip


def test_public_report_tooltip_names_genius_and_lrclib(admin_client):
    tip = _lyrics_tip(admin_client.get("/report").text)
    assert "lrclib.net" in tip


def test_admin_request_edit_tooltip_names_genius_and_lrclib(admin_client):
    pid = _pending_request_id(admin_client)
    tip = _lyrics_tip(admin_client.get(f"/admin/requests/pending/{pid}/edit").text)
    assert "lrclib.net" in tip


def test_admin_report_edit_tooltip_names_genius_and_lrclib(admin_client):
    pid = _pending_report_id(admin_client)
    tip = _lyrics_tip(admin_client.get(f"/admin/reports/pending/{pid}/edit").text)
    assert "lrclib.net" in tip


def test_report_forms_label_the_field_as_a_plain_lyrics_link(admin_client):
    assert "Genius lyrics link" not in admin_client.get("/report").text
    pid = _pending_report_id(admin_client)
    assert "Genius lyrics link" not in admin_client.get(f"/admin/reports/pending/{pid}/edit").text


def test_missing_lyrics_link_message_names_both_sites(admin_client):
    pid = _pending_report_id(admin_client)
    r = admin_client.post(f"/admin/reports/pending/{pid}/admit")
    assert r.status_code == 422
    assert "Please provide a genius.com or lrclib.net lyrics link." in r.text


# ---------------------------------------------------------------- accepting
def test_public_report_accepts_an_lrclib_link(admin_client):
    r = admin_client.post(
        "/report",
        data={
            "song_folder": _FOLDER, "category": "lyrics", "description": "wrong words",
            "language": "en", "genius_url": _LRCLIB,
        },
    )
    assert r.status_code == 200
    with SessionLocal() as db:
        assert db.query(PendingBrokenReport).one().genius_url == _LRCLIB


def test_admin_report_admit_accepts_an_lrclib_link(admin_client):
    pid = _pending_report_id(admin_client)
    r = admin_client.post(
        f"/admin/reports/pending/{pid}/edit",
        data={
            "song_folder": _FOLDER, "category": "audio", "description": "cuts out",
            "language": "en", "genius_url": _LRCLIB,
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    r = admin_client.post(f"/admin/reports/pending/{pid}/admit", follow_redirects=False)
    assert r.status_code == 303


def test_public_request_accepts_an_lrclib_link(admin_client):
    r = admin_client.post(
        "/request", data={"band_name": "Queen", "song_name": "Innuendo", "lyrics_url": _LRCLIB},
    )
    assert r.status_code == 200
    with SessionLocal() as db:
        assert db.query(PendingSongRequest).one().lyrics_url == _LRCLIB


def test_admin_request_admit_accepts_an_lrclib_link(admin_client):
    pid = _pending_request_id(admin_client)
    r = admin_client.post(
        f"/admin/requests/pending/{pid}/edit",
        data={"band_name": "Queen", "song_name": "Innuendo", "lyrics_url": _LRCLIB, **_REQUEST_ADMIN_FIELDS},
        follow_redirects=False,
    )
    assert r.status_code == 303
    r = admin_client.post(f"/admin/requests/pending/{pid}/admit", follow_redirects=False)
    assert r.status_code == 303


def test_csv_import_accepts_an_lrclib_link(admin_client):
    body = f"Queen,Bohemian Rhapsody,lyrics,wrong words,{_LRCLIB},en,,,\n".encode()
    admin_client.post("/admin/reports/import", files={"file": ("broken.csv", body, "text/csv")})
    with SessionLocal() as db:
        assert db.query(PendingBrokenReport).one().genius_url == _LRCLIB
