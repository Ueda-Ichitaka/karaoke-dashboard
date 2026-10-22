"""Tests for file paths in a song request's YouTube field
(app/validation.py: request_field_errors, allow_file_paths): besides an
http(s) link, the admin edit forms, the admit check and the CSV import
accept a path to an .mp3 or .mp4 file - the public request form doesn't,
since guests can't know paths on the NAS.
"""

from __future__ import annotations

import pytest

from app.database import SessionLocal
from app.models import PendingSongRequest, SongRequest
from app.validation import request_field_errors

MBID = "b10bbbfc-cf9e-42e0-be17-e2c3e1d2600d"
PATH = "/volume1/music/source/Journey - Faithfully.mp4"
PATH_ERROR = "The YouTube link must start with http:// or https://, or be a path to an .mp3 or .mp4 file."


def _youtube_errors(value: str, allow_file_paths: bool) -> list[str]:
    errors = request_field_errors("Journey", "Faithfully", value, "", required=set(),
                                  allow_file_paths=allow_file_paths)
    return [e for e in errors if "YouTube" in e]


@pytest.mark.parametrize("value", [PATH, "/music/song.MP3", r"C:\music\song.mp4", "song.mp3",
                                   "https://www.youtube.com/watch?v=abc"])
def test_admins_may_use_an_mp3_or_mp4_path(value):
    assert _youtube_errors(value, allow_file_paths=True) == []


@pytest.mark.parametrize("value", ["/music/song.wav", "/music/song.mp3.txt", "ftp://host/song.mp3", "song"])
def test_other_values_are_refused_for_admins(value):
    assert _youtube_errors(value, allow_file_paths=True) == [PATH_ERROR]


def test_the_public_form_only_takes_links():
    assert _youtube_errors(PATH, allow_file_paths=False) == [
        "The YouTube link must start with http:// or https://"]


def _edit_data(**overrides) -> dict[str, str]:
    data = {"band_name": "Journey", "song_name": "Faithfully", "youtube_url": PATH, "language": "en",
            "musicbrainz_id": MBID, "lyrics_url": "https://genius.com/Journey-faithfully-lyrics", "cover_url": "",
            "duet": "no"}
    data.update(overrides)
    return data


def _add(model) -> int:
    with SessionLocal() as db:
        row = model(band_name="Journey", song_name="Faithfully", requester_username="admin")
        db.add(row)
        db.commit()
        return row.id


def test_the_public_request_form_refuses_a_path(admin_client):
    r = admin_client.post("/request", data={"band_name": "Journey", "song_name": "Faithfully",
                                            "youtube_url": PATH, "duet": "no"})
    assert "The YouTube link must start with http:// or https://" in r.text
    with SessionLocal() as db:
        assert db.query(PendingSongRequest).count() == 0


def test_the_pending_edit_form_saves_and_admits_a_path(admin_client):
    pending_id = _add(PendingSongRequest)
    r = admin_client.post(f"/admin/requests/pending/{pending_id}/edit", data=_edit_data(after_save="admit"),
                          follow_redirects=False)
    assert r.status_code == 303
    with SessionLocal() as db:
        assert db.query(SongRequest).one().youtube_url == PATH


def test_the_admitted_edit_form_saves_a_path(admin_client):
    request_id = _add(SongRequest)
    admin_client.post(f"/admin/requests/{request_id}/edit", data=_edit_data())
    with SessionLocal() as db:
        assert db.get(SongRequest, request_id).youtube_url == PATH


def test_the_admin_edit_form_field_takes_text_and_says_so(admin_client):
    html = admin_client.get(f"/admin/requests/pending/{_add(PendingSongRequest)}/edit").text
    assert '<input type="text" name="youtube_url"' in html
    assert "YouTube link or media file" in html


def test_the_csv_import_takes_a_path(admin_client):
    body = ("band name,song name,youtube link,language,musicbrainz_id,lyrics_url,cover_url,duet,genre,trait\n"
            f'Journey,Faithfully,{PATH},en,,,,no,"",""\n')
    r = admin_client.post("/admin/requests/import", files={"file": ("r.csv", body.encode(), "text/csv")})
    assert "1 imported" in r.text
    with SessionLocal() as db:
        assert db.query(PendingSongRequest).one().youtube_url == PATH
