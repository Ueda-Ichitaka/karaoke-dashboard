"""Tests for importing song requests from a CSV in the existing
song-requests.csv export format (app/request_import.py, POST
/admin/requests/import). Each usable row becomes a *pending* request (Needs
review). A song never gets a second request: a row for the same band, song
and duet setting as a pending or open request merges into it by the rules
shared with the report import (app/import_merge.py). Songs already in the
library and requests already done are skipped.
"""

from __future__ import annotations

from app.database import SessionLocal
from app.models import PendingSongRequest, SongRequest

HEADER = "band name,song name,youtube link,language,musicbrainz_id,lyrics_url,cover_url,duet,genre,trait\n"
YOUTUBE = "https://www.youtube.com/watch?v=abc"
MBID = "b10bbbfc-cf9e-42e0-be17-e2c3e1d2600d"
GENIUS = "https://genius.com/Journey-faithfully-lyrics"
LRCLIB = "https://lrclib.net/tracks/42"


def _row(band="Journey", song="Faithfully", youtube="", language="", mbid="", lyrics="", cover="", duet="no",
         genre="", trait=""):
    return f'{band},{song},{youtube},{language},{mbid},{lyrics},{cover},{duet},"{genre}","{trait}"\n'


def _import(admin_client, text: str | bytes, filename: str = "song-requests.csv"):
    body = text.encode("utf-8") if isinstance(text, str) else text
    return admin_client.post("/admin/requests/import", files={"file": (filename, body, "text/csv")})


def _pending() -> list[PendingSongRequest]:
    with SessionLocal() as db:
        return db.query(PendingSongRequest).order_by(PendingSongRequest.id).all()


def test_import_page_is_linked_from_requests_and_admin_only(admin_client):
    assert "/admin/requests/import" in admin_client.get("/admin/requests").text
    page = admin_client.get("/admin/requests/import")
    assert page.status_code == 200
    assert 'action="/admin/requests/import"' in page.text
    assert 'href="/admin/requests">Back to requests</a>' in page.text

    admin_client.post("/admin/users", data={"username": "gus", "password": "gusgusgusgus"})
    admin_client.post("/logout")
    admin_client.post("/login", data={"username": "gus", "password": "gusgusgusgus"}, follow_redirects=False)
    assert admin_client.get("/admin/requests/import").status_code == 403
    assert _import(admin_client, HEADER).status_code == 403


def test_imports_a_row_with_every_field_as_a_pending_request(admin_client):
    r = _import(admin_client, HEADER + _row(
        youtube=YOUTUBE, language="en", mbid=f"https://musicbrainz.org/recording/{MBID}", lyrics=GENIUS,
        cover="https://example.com/c.jpg", duet="yes", genre="rock,pop", trait="choir",
    ))
    assert r.status_code == 200
    assert "1 imported" in r.text
    [row] = _pending()
    assert (row.band_name, row.song_name, row.youtube_url, row.language, row.musicbrainz_id, row.lyrics_url,
            row.cover_url, row.duet, row.genre, row.trait) == (
        "Journey", "Faithfully", YOUTUBE, "en", MBID, GENIUS, "https://example.com/c.jpg", "yes", "rock,pop", "choir",
    )
    assert row.requester_username == "admin"
    with SessionLocal() as db:
        assert db.query(SongRequest).count() == 0  # never straight into the exportable list


def test_unusable_rows_are_skipped_with_a_reason_and_the_rest_still_imports(admin_client):
    r = _import(admin_client, HEADER + (
        _row(band="")
        + _row(youtube="not-a-link")
        + _row(language="zz")
        + _row(cover="ftp://c.jpg")
        + _row(duet="maybe")
        + _row(genre="not-a-genre")
        + _row(trait="not-a-trait")
        + _row(band="Queen", song="Bohemian Rhapsody")
        + _row(band="Toto", song="Hold The Line")
    ))
    assert "1 imported" in r.text
    assert "8 skipped" in r.text
    for reason in (
        "Band name is required", "YouTube link must start with http", "Unrecognized language",
        "cover image link must start with http", "Unrecognized duet choice", "Unrecognized genre",
        "Unrecognized trait", "already in the library",
    ):
        assert reason in r.text
    assert [p.song_name for p in _pending()] == ["Hold The Line"]


def test_a_request_already_done_is_skipped(admin_client):
    with SessionLocal() as db:
        db.add(SongRequest(band_name="Journey", song_name="Faithfully", duet="no", status="done",
                           requester_username="admin"))
        db.commit()
    r = _import(admin_client, HEADER + _row())
    assert "1 skipped" in r.text
    assert "already done" in r.text
    assert _pending() == []


def test_plain_and_duet_rows_for_the_same_song_stay_separate(admin_client):
    _import(admin_client, HEADER + _row(duet="no") + _row(duet="yes"))
    assert sorted(p.duet for p in _pending()) == ["no", "yes"]


def test_importing_the_same_file_twice_changes_nothing(admin_client):
    text = HEADER + _row(youtube=YOUTUBE, language="en", genre="rock")
    _import(admin_client, text)
    r = _import(admin_client, text)
    assert "0 imported, 1 merged" in r.text
    assert len(_pending()) == 1


def test_missing_fields_are_filled_in_and_genres_combined(admin_client):
    _import(admin_client, HEADER + _row(genre="rock"))
    _import(admin_client, HEADER + _row(youtube=YOUTUBE, language="en", mbid=MBID, cover="https://example.com/c.jpg",
                                        genre="pop", trait="choir"))
    [row] = _pending()
    assert (row.youtube_url, row.language, row.musicbrainz_id, row.cover_url, row.genre, row.trait) == (
        YOUTUBE, "en", MBID, "https://example.com/c.jpg", "rock,pop", "choir",
    )


def test_an_lrclib_link_replaces_another_lyrics_link(admin_client):
    _import(admin_client, HEADER + _row(lyrics=GENIUS) + _row(lyrics=LRCLIB))
    assert _pending()[0].lyrics_url == LRCLIB


def test_differing_values_keep_the_existing_one_and_are_listed(admin_client):
    _import(admin_client, HEADER + _row(youtube=YOUTUBE, language="en", mbid=MBID, cover="https://example.com/a.jpg"))
    r = _import(admin_client, HEADER + _row(youtube="https://youtu.be/other", language="de",
                                            mbid="aaaaaaaa-cf9e-42e0-be17-e2c3e1d2600d",
                                            cover="https://example.com/b.jpg"))
    [row] = _pending()
    assert (row.youtube_url, row.language, row.musicbrainz_id, row.cover_url) == (
        YOUTUBE, "en", MBID, "https://example.com/a.jpg",
    )
    for label in ("YouTube link differs", "language differs", "MusicBrainz ID differs", "cover link differs"):
        assert label in r.text
    assert "Line 2: Journey - Faithfully" in r.text


def test_a_row_merges_into_an_open_admitted_request(admin_client):
    with SessionLocal() as db:
        db.add(SongRequest(band_name="Journey", song_name="Faithfully", duet="no", requester_username="admin"))
        db.commit()
    _import(admin_client, HEADER + _row(band="journey", song="faithfully", lyrics=LRCLIB))
    assert _pending() == []
    with SessionLocal() as db:
        assert db.query(SongRequest).one().lyrics_url == LRCLIB


def test_round_trip_export_then_import_keeps_every_field(admin_client):
    with SessionLocal() as db:
        db.add(SongRequest(
            band_name="Journey", song_name="Faithfully", youtube_url=YOUTUBE, language="en", musicbrainz_id=MBID,
            lyrics_url=GENIUS, cover_url="https://example.com/c.jpg", duet="yes", genre="rock,pop",
            trait="choir", requester_username="admin",
        ))
        db.commit()
    exported = admin_client.get("/admin/requests.csv").content
    with SessionLocal() as db:
        db.query(SongRequest).delete()
        db.commit()

    _import(admin_client, exported)
    [row] = _pending()
    assert (row.youtube_url, row.language, row.musicbrainz_id, row.lyrics_url, row.cover_url, row.duet,
            row.genre, row.trait) == (YOUTUBE, "en", MBID, GENIUS, "https://example.com/c.jpg", "yes", "rock,pop",
                                      "choir")
