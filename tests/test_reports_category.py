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
    assert broken_report_field_errors("audio", "") == []


def test_description_required_when_category_is_other():
    errors = broken_report_field_errors("other", "")
    assert any("describe" in e.lower() for e in errors)
    assert broken_report_field_errors("other", "the whole track is silent") == []


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
        data={"song_folder": "Queen - Bohemian Rhapsody", "category": "audio", "description": ""},
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
        data={"song_folder": "Queen - Bohemian Rhapsody", "category": "lyrics", "description": ""},
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
        },
    )
    r = admin_client.get("/admin/reports.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert 'filename="broken.csv"' in r.headers["content-disposition"]
    body = r.text
    assert body.startswith("band,song name,category,description\n")
    assert "Queen,Bohemian Rhapsody,async,drifts after 1 minute\n" in body


def test_broken_csv_requires_admin(admin_client):
    admin_client.post("/admin/users", data={"username": "greg", "password": "greggreggreg"})
    admin_client.post("/logout")
    admin_client.post("/login", data={"username": "greg", "password": "greggreggreg"}, follow_redirects=False)
    assert admin_client.get("/admin/reports.csv").status_code == 403
