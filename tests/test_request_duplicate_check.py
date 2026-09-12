"""Tests for checking whether a requested song already exists in the
library, via a naive "band - song" folder-name lookup: songs.folder_exists(),
the live-check endpoint used by the request form's progressive enhancement,
and the server-side rejection on submit (so the check can't be bypassed by
skipping JS).
"""

from __future__ import annotations

from app import songs


def test_folder_exists_matches_case_insensitively():
    assert songs.folder_exists("queen", "bohemian rhapsody") == "Queen - Bohemian Rhapsody"
    assert songs.folder_exists("  Queen  ", "  Bohemian Rhapsody  ") == "Queen - Bohemian Rhapsody"


def test_folder_exists_returns_none_for_new_song():
    assert songs.folder_exists("Journey", "Faithfully") is None


def test_request_check_endpoint_reports_existing_song(admin_client):
    r = admin_client.get("/request/check", params={"band_name": "Queen", "song_name": "Bohemian Rhapsody"})
    assert r.status_code == 200
    data = r.json()
    assert data == {"exists": True, "folder": "Queen - Bohemian Rhapsody"}


def test_request_check_endpoint_reports_new_song(admin_client):
    r = admin_client.get("/request/check", params={"band_name": "Journey", "song_name": "Faithfully"})
    assert r.status_code == 200
    assert r.json() == {"exists": False, "folder": None}


def test_request_check_requires_login(client):
    r = client.get(
        "/request/check",
        params={"band_name": "Queen", "song_name": "Bohemian Rhapsody"},
        follow_redirects=False,
    )
    assert r.status_code == 303


def test_request_submit_rejected_when_song_already_in_library(admin_client):
    r = admin_client.post("/request", data={"band_name": "Queen", "song_name": "Bohemian Rhapsody"})
    assert r.status_code == 422
    assert "already" in r.text.lower()
    assert "library" in r.text.lower()


def test_request_form_wires_up_live_duplicate_check(admin_client):
    r = admin_client.get("/request")
    assert "data-duplicate-check" in r.text
    assert "/request/check" in r.text
    assert 'data-dup-field="band"' in r.text
    assert 'data-dup-field="song"' in r.text
