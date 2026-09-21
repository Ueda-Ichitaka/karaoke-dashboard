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
    assert 'value="mixed"' in r.text and "Mixed" in r.text
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


def test_request_accepts_a_pasted_musicbrainz_url_instead_of_a_bare_id(admin_client):
    # This used to overflow the musicbrainz_id column (VARCHAR(64)) and
    # crash the request - the URL alone is 71 chars.
    r = admin_client.post(
        "/request",
        data={
            "band_name": "Lacrimosa",
            "song_name": "Lichtgestalt",
            "musicbrainz_id": "https://musicbrainz.org/recording/2fa14ea5-9e94-4a6c-9c62-3c0dc9ce6b8f",
        },
    )
    assert r.status_code == 200
    assert "was submitted" in r.text

    r = admin_client.get("/admin/requests.csv", params={"scope": "all"})
    assert "2fa14ea5-9e94-4a6c-9c62-3c0dc9ce6b8f" in r.text
    assert "musicbrainz.org" not in r.text


def test_request_rejects_an_unreasonably_long_musicbrainz_value(admin_client):
    r = admin_client.post(
        "/request",
        data={"band_name": "Journey", "song_name": "Faithfully", "musicbrainz_id": "x" * 100},
    )
    assert r.status_code == 422
    assert "musicbrainz" in r.text.lower()


def test_requests_csv_neutralizes_formula_injection_in_band_and_song_name(admin_client):
    admin_client.post(
        "/request",
        data={"band_name": '=cmd|"/c calc"!A0', "song_name": "+1+1", "musicbrainz_id": "-DDE(1)"},
    )
    r = admin_client.get("/admin/requests.csv", params={"scope": "all"})
    body = r.text
    assert "'=cmd" in body
    assert "'+1+1" in body
    assert "'-DDE(1)" in body
    # a formula-triggering field must never start right after the opening
    # quote/comma - it must always be preceded by the defusing "'" first
    assert '"=cmd' not in body
    assert ",+1+1" not in body
    assert ",-DDE(1)" not in body


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
    assert body.startswith("band name,song name,youtube link,language,musicbrainz_id,lyrics_url,cover_url,duet\n")
    assert (
        "Lacrimosa,Lichtgestalt,,de,mbid-123,https://genius.com/Lacrimosa-lichtgestalt-lyrics,,\n"
        in body
    )
    # optional columns stay blank, not "None", when unset
    assert "Journey,Faithfully,,,,,,\n" in body


# ------------------------------------------------------- cover image + duet
def test_request_form_shows_cover_url_and_duet_fields(admin_client):
    r = admin_client.get("/request")
    assert 'name="cover_url"' in r.text
    assert '<select name="duet"' in r.text
    assert 'value="yes"' in r.text and 'value="no"' in r.text


def test_request_submit_accepts_cover_url_and_duet(admin_client):
    r = admin_client.post(
        "/request",
        data={
            "band_name": "Lacrimosa", "song_name": "Lichtgestalt",
            "cover_url": "https://example.com/cover.jpg", "duet": "yes",
        },
    )
    assert r.status_code == 200
    assert "was submitted" in r.text


def test_request_rejects_a_cover_url_that_is_not_http(admin_client):
    r = admin_client.post(
        "/request",
        data={"band_name": "Journey", "song_name": "Faithfully", "cover_url": "cover.jpg"},
    )
    assert r.status_code == 422
    assert "cover" in r.text.lower()


def test_request_rejects_an_unknown_duet_value(admin_client):
    r = admin_client.post(
        "/request",
        data={"band_name": "Journey", "song_name": "Faithfully", "duet": "maybe"},
    )
    assert r.status_code == 422
    assert "duet" in r.text.lower()


def test_requests_csv_exports_cover_url_and_duet_columns(admin_client):
    admin_client.post(
        "/request",
        data={
            "band_name": "Lacrimosa", "song_name": "Lichtgestalt",
            "cover_url": "https://example.com/cover.jpg", "duet": "yes",
        },
    )
    admin_client.post(
        "/request", data={"band_name": "Journey", "song_name": "Faithfully", "duet": "no"}
    )
    body = admin_client.get("/admin/requests.csv", params={"scope": "all"}).text
    assert body.startswith(
        "band name,song name,youtube link,language,musicbrainz_id,lyrics_url,cover_url,duet\n"
    )
    assert "Lacrimosa,Lichtgestalt,,,,,https://example.com/cover.jpg,yes\n" in body
    assert "Journey,Faithfully,,,,,,no\n" in body
