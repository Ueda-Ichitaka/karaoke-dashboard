"""Tests for the security-headers middleware (app/main.py): defends the
login page (and every other page) against clickjacking and MIME-sniffing,
regardless of which route served the response.
"""

from __future__ import annotations


def test_login_page_has_clickjacking_and_mime_sniffing_headers(client):
    r = client.get("/login")
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "same-origin"


def test_headers_present_on_api_style_responses_too(admin_client):
    r = admin_client.get("/request/check", params={"band_name": "a", "song_name": "b"})
    assert r.headers["x-frame-options"] == "DENY"


def test_headers_present_on_streaming_csv_export(admin_client):
    r = admin_client.get("/admin/requests.csv")
    assert r.headers["x-frame-options"] == "DENY"
    assert r.status_code == 200
