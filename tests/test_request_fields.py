"""Tests for the optional language/musicbrainz_id/lyrics_url song-request
fields requested upstream (see UPSTREAM_REQUESTS.md): the request form, its
validation, and the requests.csv export.
"""

from __future__ import annotations


def test_request_form_shows_language_select_and_tooltips(admin_client):
    r = admin_client.get("/request")
    assert r.status_code == 200
    assert '<select name="language"' in r.text
    assert 'value="de"' in r.text and "German" in r.text
    # tooltip hints on the two upstream-only fields - a CSS-driven tooltip
    # (data-tip), not the native title="" attribute, which browsers render
    # inconsistently (and not at all on some setups/devices)
    assert 'name="musicbrainz_id"' in r.text
    assert 'name="lyrics_url"' in r.text
    assert r.text.count('class="field-hint"') == 2
    assert 'title="' not in r.text
    assert "MusicBrainz recording or release ID" in r.text
    assert "genius.com" in r.text


def test_request_submit_accepts_optional_upstream_fields(admin_client):
    r = admin_client.post(
        "/request",
        data={
            "band_name": "Lacrimosa",
            "song_name": "Lichtgestalt",
            "youtube_url": "https://www.youtube.com/watch?v=XYZ",
            "language": "de",
            "musicbrainz_id": "b9c2c3f0-something",
            "lyrics_url": "https://genius.com/Lacrimosa-lichtgestalt-lyrics",
        },
    )
    assert r.status_code == 200
    assert "was submitted" in r.text


def test_request_submit_all_upstream_fields_optional(admin_client):
    r = admin_client.post(
        "/request",
        data={"band_name": "Journey", "song_name": "Faithfully"},
    )
    assert r.status_code == 200


def test_request_rejects_unknown_language_code(admin_client):
    r = admin_client.post(
        "/request",
        data={"band_name": "Journey", "song_name": "Faithfully", "language": "xx"},
    )
    assert r.status_code == 422
    assert "language" in r.text.lower()


def test_lyrics_url_accepts_filesystem_path(admin_client):
    # admins may point lyrics_url at a file on disk, not just a URL
    r = admin_client.post(
        "/request",
        data={
            "band_name": "Journey",
            "song_name": "Faithfully",
            "lyrics_url": "/songs/Journey - Faithfully/lyrics.txt",
        },
    )
    assert r.status_code == 200
    assert "was submitted" in r.text


def test_requests_csv_includes_upstream_columns(admin_client):
    admin_client.post(
        "/request",
        data={
            "band_name": "Lacrimosa",
            "song_name": "Lichtgestalt",
            "language": "de",
            "musicbrainz_id": "mbid-123",
            "lyrics_url": "https://genius.com/Lacrimosa-lichtgestalt-lyrics",
        },
    )
    admin_client.post("/request", data={"band_name": "Journey", "song_name": "Faithfully"})

    r = admin_client.get("/admin/requests.csv", params={"scope": "all"})
    assert r.status_code == 200
    body = r.text
    assert body.startswith("band name,song name,youtube link,language,musicbrainz_id,lyrics_url\n")
    assert (
        "Lacrimosa,Lichtgestalt,,de,mbid-123,https://genius.com/Lacrimosa-lichtgestalt-lyrics\n"
        in body
    )
    # optional columns stay blank, not "None", when unset
    assert "Journey,Faithfully,,,,\n" in body
