"""Tests for the lyrics field rule (app/validation.py: lyrics_link_error) on
song requests (lyrics_url) and broken-song reports (genius_url, exported as
lyrics_url): only a genius.com song page or an lrclib.net track page - the
pages the song pipeline can use. The admin side (edit forms, admit checks,
CSV imports) also takes a path to a .txt file; the public forms don't.
"""

from __future__ import annotations

import pytest

from app.database import SessionLocal
from app.models import BrokenReport, PendingBrokenReport, PendingSongRequest, SongRequest
from app.validation import broken_report_field_errors, lyrics_link_error, request_field_errors

LINK_ERROR = ("The lyrics link must be a genius.com song page (genius.com/...-lyrics) "
              "or an lrclib.net track page (lrclib.net/tracks/...).")
PATH_ERROR = ("The lyrics link must be a genius.com song page (genius.com/...-lyrics), "
              "an lrclib.net track page (lrclib.net/tracks/...) or a path to a .txt file.")
TXT_PATH = "/volume1/karaoke/lyrics/Journey - Faithfully.txt"
FOLDER = "Queen - Bohemian Rhapsody"
MBID = "b10bbbfc-cf9e-42e0-be17-e2c3e1d2600d"


@pytest.mark.parametrize("value", [
    "https://genius.com/Journey-faithfully-lyrics",
    "http://www.genius.com/Journey-faithfully-lyrics/",
    "https://genius.com/Queen-bohemian-rhapsody-lyrics?utm=x",
    "https://lrclib.net/tracks/123456",
    "https://www.lrclib.net/tracks/42/",
    "HTTPS://LRCLIB.NET/tracks/7",
])
def test_song_and_track_pages_are_accepted_everywhere(value):
    assert lyrics_link_error(value, allow_file_paths=False) is None
    assert lyrics_link_error(value, allow_file_paths=True) is None


@pytest.mark.parametrize("value", [
    "https://genius.com/artists/Journey",
    "https://genius.com/albums/Journey/Raised-on-radio",
    "https://genius.com/",
    "https://lrclib.net/search?q=faithfully",
    "https://lrclib.net/tracks/abc",
    "https://www.azlyrics.com/lyrics/journey/faithfully.html",
    "https://evil.example/genius.com/Journey-faithfully-lyrics",
    "https://genius.com.evil.example/Journey-faithfully-lyrics",
    "https://example.com/lyrics.txt",
    "ftp://lrclib.net/tracks/1",
])
def test_other_links_are_refused(value):
    assert lyrics_link_error(value, allow_file_paths=False) == LINK_ERROR
    assert lyrics_link_error(value, allow_file_paths=True) == PATH_ERROR


@pytest.mark.parametrize("value", [TXT_PATH, "lyrics.TXT", r"C:\lyrics\song.txt"])
def test_txt_paths_only_on_the_admin_side(value):
    assert lyrics_link_error(value, allow_file_paths=False) == LINK_ERROR
    assert lyrics_link_error(value, allow_file_paths=True) is None


@pytest.mark.parametrize("value", ["/lyrics/song.lrc", "/lyrics/song.txt.bak", "lyrics"])
def test_other_paths_are_refused(value):
    assert lyrics_link_error(value, allow_file_paths=True) == PATH_ERROR


def test_an_empty_field_is_left_to_the_required_check():
    assert lyrics_link_error("", allow_file_paths=False) is None


def test_both_field_checks_use_the_rule():
    assert LINK_ERROR in request_field_errors("A", "B", "", "", lyrics_url=TXT_PATH, required=set())
    assert LINK_ERROR not in request_field_errors("A", "B", "", "", lyrics_url=TXT_PATH, required=set(),
                                                  allow_file_paths=True)
    assert LINK_ERROR in broken_report_field_errors("lyrics", "x", TXT_PATH, required=set())
    assert broken_report_field_errors("lyrics", "x", TXT_PATH, required=set(), allow_file_paths=True) == []


# ---- the forms and imports ----
def test_the_public_request_form_refuses_another_site(admin_client):
    r = admin_client.post("/request", data={"band_name": "Journey", "song_name": "Faithfully", "duet": "no",
                                            "lyrics_url": "https://www.azlyrics.com/x.html"})
    assert LINK_ERROR in r.text.replace("&#39;", "'")
    with SessionLocal() as db:
        assert db.query(PendingSongRequest).count() == 0


def test_the_public_report_form_refuses_a_path(admin_client):
    r = admin_client.post("/report", data={"song_folder": FOLDER, "category": "lyrics", "description": "x",
                                           "language": "en", "genius_url": TXT_PATH})
    assert LINK_ERROR in r.text
    with SessionLocal() as db:
        assert db.query(PendingBrokenReport).count() == 0


def test_the_admin_request_edit_saves_a_txt_path(admin_client):
    with SessionLocal() as db:
        row = SongRequest(band_name="Journey", song_name="Faithfully", requester_username="admin")
        db.add(row)
        db.commit()
        request_id = row.id
    admin_client.post(f"/admin/requests/{request_id}/edit", data={
        "band_name": "Journey", "song_name": "Faithfully", "youtube_url": "https://youtu.be/x", "language": "en",
        "musicbrainz_id": MBID, "lyrics_url": TXT_PATH, "duet": "no"})
    with SessionLocal() as db:
        assert db.get(SongRequest, request_id).lyrics_url == TXT_PATH


def test_the_admin_report_edit_saves_and_admits_a_txt_path(admin_client):
    with SessionLocal() as db:
        row = PendingBrokenReport(song_folder=FOLDER, category="lyrics", description="x", reporter_username="admin")
        db.add(row)
        db.commit()
        pending_id = row.id
    html = admin_client.get(f"/admin/reports/pending/{pending_id}/edit").text
    assert '<input type="text" name="genius_url"' in html
    admin_client.post(f"/admin/reports/pending/{pending_id}/edit", data={
        "song_folder": FOLDER, "category": "lyrics", "description": "x", "language": "en",
        "genius_url": TXT_PATH, "after_save": "admit"})
    with SessionLocal() as db:
        assert db.query(BrokenReport).one().genius_url == TXT_PATH


def test_the_report_import_takes_a_txt_path_and_refuses_another_site(admin_client):
    body = ("band,song name,category,description,lyrics_url,language,cover_url,genre,trait\n"
            f"Queen,Bohemian Rhapsody,lyrics,x,{TXT_PATH},en,,,\n"
            "Toto,Africa,lyrics,x,https://www.azlyrics.com/x.html,en,,,\n")
    r = admin_client.post("/admin/reports/import", files={"file": ("b.csv", body.encode(), "text/csv")})
    assert "1 imported" in r.text
    assert "1 skipped" in r.text
    with SessionLocal() as db:
        assert db.query(PendingBrokenReport).one().genius_url == TXT_PATH


def test_the_request_import_takes_a_txt_path(admin_client):
    body = ("band name,song name,youtube link,language,musicbrainz_id,lyrics_url,cover_url,duet,genre,trait\n"
            f'Journey,Faithfully,,en,,{TXT_PATH},,no,"",""\n')
    admin_client.post("/admin/requests/import", files={"file": ("r.csv", body.encode(), "text/csv")})
    with SessionLocal() as db:
        assert db.query(PendingSongRequest).one().lyrics_url == TXT_PATH
