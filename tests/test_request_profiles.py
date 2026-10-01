"""Tests for the karaoke-night/strict profile switch on the request-song
form (app/profiles.py, app/app_settings.py) and the new pending-review
workflow: a submission now lands in PendingSongRequest, not SongRequest,
until an admin admits it (see app/routes/admin.py).
"""

from __future__ import annotations

from app.database import SessionLocal
from app.models import PendingSongRequest, SongRequest


def _set_request_profile(admin_client, profile: str) -> None:
    admin_client.post(
        "/admin/settings", data={"request_profile": profile, "report_profile": "strict"}
    )


def test_karaoke_night_is_the_default_and_only_requires_band_and_song(admin_client):
    r = admin_client.get("/request")
    assert r.status_code == 200
    assert '<input type="url" name="youtube_url"' in r.text
    assert 'name="youtube_url" required' not in r.text
    assert '<select name="language" required' not in r.text
    assert 'name="lyrics_url" required' not in r.text


def test_strict_profile_marks_youtube_language_lyrics_as_required(admin_client):
    _set_request_profile(admin_client, "strict")
    r = admin_client.get("/request")
    assert 'name="youtube_url" required' in r.text
    assert '<select name="language" required' in r.text
    assert 'name="lyrics_url" required' in r.text


def test_strict_profile_rejects_submission_missing_those_fields(admin_client):
    _set_request_profile(admin_client, "strict")
    r = admin_client.post("/request", data={"band_name": "Journey", "song_name": "Faithfully"})
    assert r.status_code == 422
    assert "youtube" in r.text.lower()
    assert "language" in r.text.lower()
    assert "lyrics" in r.text.lower()


def test_strict_profile_accepts_submission_with_all_fields(admin_client):
    _set_request_profile(admin_client, "strict")
    r = admin_client.post(
        "/request",
        data={
            "band_name": "Journey", "song_name": "Faithfully",
            "youtube_url": "https://www.youtube.com/watch?v=x",
            "language": "en", "lyrics_url": "https://genius.com/journey-faithfully-lyrics",
        },
    )
    assert r.status_code == 200
    assert "was submitted" in r.text


def test_karaoke_night_submission_with_only_band_and_song_succeeds(admin_client):
    r = admin_client.post("/request", data={"band_name": "Journey", "song_name": "Faithfully"})
    assert r.status_code == 200
    assert "was submitted" in r.text


# ------------------------------------------------------------ pending table
def test_submission_lands_in_the_pending_table_not_the_admitted_one(admin_client):
    admin_client.post("/request", data={"band_name": "Journey", "song_name": "Faithfully"})
    with SessionLocal() as db:
        assert db.query(PendingSongRequest).count() == 1
        assert db.query(SongRequest).count() == 0
