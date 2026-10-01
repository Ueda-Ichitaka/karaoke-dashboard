"""Tests for the karaoke-night/strict profile switch on the report-broken
form (app/profiles.py, app/app_settings.py) and the pending-review
workflow: a submission now lands in PendingBrokenReport, not BrokenReport,
until an admin admits it (see app/routes/admin.py).
"""

from __future__ import annotations

from app.database import SessionLocal
from app.models import BrokenReport, PendingBrokenReport


def _set_report_profile(admin_client, profile: str) -> None:
    admin_client.post(
        "/admin/settings", data={"request_profile": "karaoke_night", "report_profile": profile}
    )


def test_strict_is_the_default_and_requires_language(admin_client):
    r = admin_client.get("/report")
    assert '<select name="language" required' in r.text


def test_karaoke_night_relaxes_language_and_genius_but_keeps_description(admin_client):
    _set_report_profile(admin_client, "karaoke_night")
    r = admin_client.get("/report")
    assert '<select name="language" required' not in r.text
    assert 'name="genius_url" required' not in r.text
    assert '<textarea name="description" rows="4" required' in r.text


def test_karaoke_night_submission_without_language_or_genius_succeeds(admin_client):
    _set_report_profile(admin_client, "karaoke_night")
    r = admin_client.post(
        "/report",
        data={
            "song_folder": "Queen - Bohemian Rhapsody", "category": "lyrics",
            "description": "lyrics are wrong",
        },
    )
    assert r.status_code == 200
    assert "was submitted" in r.text


def test_karaoke_night_submission_without_description_still_fails(admin_client):
    _set_report_profile(admin_client, "karaoke_night")
    r = admin_client.post(
        "/report",
        data={"song_folder": "Queen - Bohemian Rhapsody", "category": "audio", "description": ""},
    )
    assert r.status_code == 422
    assert "describe" in r.text.lower()


def test_strict_submission_without_language_fails(admin_client):
    r = admin_client.post(
        "/report",
        data={
            "song_folder": "Queen - Bohemian Rhapsody", "category": "audio",
            "description": "cuts out",
        },
    )
    assert r.status_code == 422
    assert "language" in r.text.lower()


# ------------------------------------------------------------ pending table
def test_submission_lands_in_the_pending_table_not_the_admitted_one(admin_client):
    admin_client.post(
        "/report",
        data={
            "song_folder": "Queen - Bohemian Rhapsody", "category": "audio",
            "description": "cuts out", "language": "de",
        },
    )
    with SessionLocal() as db:
        assert db.query(PendingBrokenReport).count() == 1
        assert db.query(BrokenReport).count() == 0
