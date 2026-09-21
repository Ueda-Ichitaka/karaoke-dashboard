"""Tests for the broken-report category field: mandatory choice list (see
app/broken_categories.py), with the free-text description only required
when "other" is chosen, plus the admin broken.csv export.
"""

from __future__ import annotations

from app.validation import broken_report_field_errors


def test_category_is_required():
    errors = broken_report_field_errors("", "")
    assert any("category" in e.lower() for e in errors)


def test_unrecognized_category_is_rejected():
    errors = broken_report_field_errors("not-a-real-category", "some text")
    assert any("category" in e.lower() for e in errors)


def test_description_optional_for_a_specific_category():
    assert broken_report_field_errors("audio", "", language="de") == []


def test_description_required_when_category_is_other():
    errors = broken_report_field_errors("other", "")
    assert any("describe" in e.lower() for e in errors)
    assert broken_report_field_errors("other", "the whole track is silent", language="de") == []


def test_report_submit_requires_category(admin_client):
    r = admin_client.post(
        "/report",
        data={"song_folder": "Queen - Bohemian Rhapsody", "category": "", "description": ""},
    )
    assert r.status_code == 422
    assert "category" in r.text.lower()


def test_report_submit_with_specific_category_and_no_description_succeeds(admin_client):
    r = admin_client.post(
        "/report",
        data={
            "song_folder": "Queen - Bohemian Rhapsody", "category": "audio", "description": "",
            "language": "de",
        },
    )
    assert r.status_code == 200
    assert "was submitted" in r.text


def test_report_submit_other_category_requires_description(admin_client):
    r = admin_client.post(
        "/report",
        data={"song_folder": "Queen - Bohemian Rhapsody", "category": "other", "description": ""},
    )
    assert r.status_code == 422
    assert "describe" in r.text.lower()


def test_admin_reports_view_shows_category(admin_client):
    admin_client.post(
        "/report",
        data={
            "song_folder": "Queen - Bohemian Rhapsody", "category": "lyrics", "description": "",
            "genius_url": "https://genius.com/Queen-bohemian-rhapsody-lyrics",
            "language": "de",
        },
    )
    r = admin_client.get("/admin/reports")
    assert "Lyrics broken" in r.text


def test_broken_csv_export(admin_client):
    admin_client.post(
        "/report",
        data={
            "song_folder": "Queen - Bohemian Rhapsody",
            "category": "async",
            "description": "drifts after 1 minute",
            "genius_url": "https://genius.com/Queen-bohemian-rhapsody-lyrics",
            "language": "de",
        },
    )
    r = admin_client.get("/admin/reports.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert 'filename="broken.csv"' in r.headers["content-disposition"]
    body = r.text
    # column names are "lyrics_url"/"language" (matching the UltraSinger-side
    # asks in UPSTREAM_REQUESTS.md), even though the lyrics field is named
    # genius_url here
    assert body.startswith("band,song name,category,description,lyrics_url,language,cover_url\n")
    assert (
        "Queen,Bohemian Rhapsody,async,drifts after 1 minute,"
        "https://genius.com/Queen-bohemian-rhapsody-lyrics,de,\n"
    ) in body


def test_broken_csv_lyrics_url_column_blank_when_not_set(admin_client):
    admin_client.post(
        "/report",
        data={
            "song_folder": "Queen - Bohemian Rhapsody", "category": "audio", "description": "",
            "language": "de",
        },
    )
    r = admin_client.get("/admin/reports.csv")
    body = r.text
    assert "Queen,Bohemian Rhapsody,audio,,,de,\n" in body


# --------------------------------------------------------- genius link
def test_genius_link_required_for_lyrics_category():
    errors = broken_report_field_errors("lyrics", "", genius_url="")
    assert any("genius" in e.lower() for e in errors)


def test_genius_link_required_for_async_category():
    errors = broken_report_field_errors("async", "", genius_url="")
    assert any("genius" in e.lower() for e in errors)


def test_genius_link_not_required_for_other_categories():
    assert broken_report_field_errors("audio", "", genius_url="", language="de") == []
    assert broken_report_field_errors("video", "", genius_url="", language="de") == []


def test_genius_link_must_be_a_url_when_given():
    errors = broken_report_field_errors("lyrics", "", genius_url="not-a-url")
    assert any("http" in e.lower() for e in errors)
    assert (
        broken_report_field_errors(
            "lyrics", "", genius_url="https://genius.com/x-lyrics", language="de"
        )
        == []
    )


def test_report_submit_lyrics_category_requires_genius_link(admin_client):
    r = admin_client.post(
        "/report",
        data={"song_folder": "Queen - Bohemian Rhapsody", "category": "lyrics", "description": ""},
    )
    assert r.status_code == 422
    assert "genius" in r.text.lower()


def test_report_submit_async_category_requires_genius_link(admin_client):
    r = admin_client.post(
        "/report",
        data={"song_folder": "Queen - Bohemian Rhapsody", "category": "async", "description": ""},
    )
    assert r.status_code == 422
    assert "genius" in r.text.lower()


def test_report_submit_lyrics_category_with_genius_link_succeeds(admin_client):
    r = admin_client.post(
        "/report",
        data={
            "song_folder": "Queen - Bohemian Rhapsody", "category": "lyrics", "description": "",
            "genius_url": "https://genius.com/Queen-bohemian-rhapsody-lyrics",
            "language": "de",
        },
    )
    assert r.status_code == 200
    assert "was submitted" in r.text


def test_admin_reports_view_shows_genius_link(admin_client):
    admin_client.post(
        "/report",
        data={
            "song_folder": "Queen - Bohemian Rhapsody", "category": "lyrics", "description": "",
            "genius_url": "https://genius.com/Queen-bohemian-rhapsody-lyrics",
            "language": "de",
        },
    )
    r = admin_client.get("/admin/reports")
    assert 'href="https://genius.com/Queen-bohemian-rhapsody-lyrics"' in r.text


def test_report_form_wires_up_category_and_genius_toggle(admin_client):
    r = admin_client.get("/report")
    assert "data-broken-category" in r.text
    assert "data-broken-genius" in r.text


# ------------------------------------------------------------ sanitization
def test_report_description_is_collapsed_to_a_single_line_and_sanitized(admin_client):
    admin_client.post(
        "/report",
        data={
            "song_folder": "Queen - Bohemian Rhapsody",
            "category": "other",
            "description": "line one,\nline two; with a \"quote\" and | a pipe\r\nline three",
            "language": "de",
        },
    )
    r = admin_client.get("/admin/reports")
    assert "line one line two with a quote and a pipe line three" in r.text
    assert "\n" not in r.text.split("line one")[1].split("line three")[0]


# --------------------------------------------------------------- language
def test_language_is_required():
    errors = broken_report_field_errors(
        "audio", "", genius_url="", language=""
    )
    assert any("language" in e.lower() for e in errors)


def test_unrecognized_language_is_rejected():
    errors = broken_report_field_errors("audio", "", genius_url="", language="zz")
    assert any("language" in e.lower() for e in errors)


def test_mixed_language_is_accepted():
    assert broken_report_field_errors("audio", "", genius_url="", language="mixed") == []


def test_report_form_shows_a_required_language_select(admin_client):
    r = admin_client.get("/report")
    assert '<select name="language" required' in r.text
    assert 'value="mixed"' in r.text and "Mixed" in r.text


def test_report_submit_requires_language(admin_client):
    r = admin_client.post(
        "/report",
        data={"song_folder": "Queen - Bohemian Rhapsody", "category": "audio", "description": ""},
    )
    assert r.status_code == 422
    assert "language" in r.text.lower()


def test_report_submit_with_language_succeeds(admin_client):
    r = admin_client.post(
        "/report",
        data={
            "song_folder": "Queen - Bohemian Rhapsody", "category": "audio", "description": "",
            "language": "de",
        },
    )
    assert r.status_code == 200
    assert "was submitted" in r.text


def test_admin_reports_view_shows_language(admin_client):
    admin_client.post(
        "/report",
        data={
            "song_folder": "Queen - Bohemian Rhapsody", "category": "audio", "description": "",
            "language": "de",
        },
    )
    r = admin_client.get("/admin/reports")
    assert "German" in r.text


def test_broken_csv_includes_language_column(admin_client):
    admin_client.post(
        "/report",
        data={
            "song_folder": "Queen - Bohemian Rhapsody",
            "category": "async",
            "description": "drifts after 1 minute",
            "genius_url": "https://genius.com/Queen-bohemian-rhapsody-lyrics",
            "language": "de",
        },
    )
    r = admin_client.get("/admin/reports.csv")
    body = r.text
    assert body.startswith("band,song name,category,description,lyrics_url,language,cover_url\n")
    assert (
        "Queen,Bohemian Rhapsody,async,drifts after 1 minute,"
        "https://genius.com/Queen-bohemian-rhapsody-lyrics,de,\n"
    ) in body


def test_broken_csv_requires_admin(admin_client):
    admin_client.post("/admin/users", data={"username": "greg", "password": "greggreggreg"})
    admin_client.post("/logout")
    admin_client.post("/login", data={"username": "greg", "password": "greggreggreg"}, follow_redirects=False)
    assert admin_client.get("/admin/reports.csv").status_code == 403


# ------------------------------------------------------------- cover image
def test_cover_url_is_optional_but_must_be_http_when_given():
    assert broken_report_field_errors("audio", "", language="de", cover_url="") == []
    assert (
        broken_report_field_errors("audio", "", language="de", cover_url="https://x.org/c.png")
        == []
    )
    errors = broken_report_field_errors("audio", "", language="de", cover_url="c.png")
    assert any("cover" in e.lower() for e in errors)


def test_report_form_shows_cover_url_field(admin_client):
    assert 'name="cover_url"' in admin_client.get("/report").text


def test_report_submit_rejects_a_non_http_cover_url(admin_client):
    r = admin_client.post(
        "/report",
        data={
            "song_folder": "Queen - Bohemian Rhapsody", "category": "audio",
            "language": "de", "cover_url": "c.png",
        },
    )
    assert r.status_code == 422
    assert "cover" in r.text.lower()


def test_report_cover_url_is_shown_in_admin_and_exported(admin_client):
    r = admin_client.post(
        "/report",
        data={
            "song_folder": "Queen - Bohemian Rhapsody", "category": "audio",
            "language": "de", "cover_url": "https://example.com/cover.jpg",
        },
    )
    assert r.status_code == 200
    assert 'href="https://example.com/cover.jpg"' in admin_client.get("/admin/reports").text
    body = admin_client.get("/admin/reports.csv").text
    assert body.startswith(
        "band,song name,category,description,lyrics_url,language,cover_url\n"
    )
    assert "Queen,Bohemian Rhapsody,audio,,,de,https://example.com/cover.jpg\n" in body
