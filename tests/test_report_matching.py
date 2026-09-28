"""Tests for app/report_matching.py: finding an already-open broken-song
report for the same song (so a new report merges instead of duplicating),
and the merge itself.
"""

from __future__ import annotations

from app.database import SessionLocal
from app.models import BrokenReport
from app.report_matching import find_existing_report, merge_into_existing_report


def _insert_report(song_folder="Queen - Bohemian Rhapsody", **kwargs) -> int:
    kwargs.setdefault("category", "audio")
    kwargs.setdefault("description", "")
    with SessionLocal() as db:
        r = BrokenReport(song_folder=song_folder, reporter_username="admin", **kwargs)
        db.add(r)
        db.commit()
        db.refresh(r)
        return r.id


# ------------------------------------------------------------------- finding
def test_finds_an_open_report_for_the_same_song(admin_client):
    rid = _insert_report()
    with SessionLocal() as db:
        found = find_existing_report(db, "Queen - Bohemian Rhapsody")
        assert found is not None
        assert found.id == rid


def test_does_not_match_a_resolved_report(admin_client):
    _insert_report(status="resolved")
    with SessionLocal() as db:
        assert find_existing_report(db, "Queen - Bohemian Rhapsody") is None


def test_does_not_match_a_different_song(admin_client):
    _insert_report()
    with SessionLocal() as db:
        assert find_existing_report(db, "Toto - Africa") is None


def test_blank_song_folder_matches_nothing(admin_client):
    with SessionLocal() as db:
        assert find_existing_report(db, "") is None


# --------------------------------------------------------------------- merge
def _report(**kwargs) -> BrokenReport:
    kwargs.setdefault("song_folder", "x")
    kwargs.setdefault("category", "audio")
    kwargs.setdefault("description", "")
    kwargs.setdefault("reporter_username", "a")
    return BrokenReport(**kwargs)


def test_merge_fills_in_missing_lyrics_and_cover_links():
    existing = _report()
    merge_into_existing_report(
        existing, category="audio", description="", genius_url="https://genius.com/a", cover_url="https://x/c.jpg"
    )
    assert existing.genius_url == "https://genius.com/a"
    assert existing.cover_url == "https://x/c.jpg"


def test_merge_does_not_overwrite_an_existing_link():
    existing = _report(genius_url="https://genius.com/original", cover_url="https://x/original.jpg")
    merge_into_existing_report(
        existing, category="audio", description="",
        genius_url="https://genius.com/new", cover_url="https://x/new.jpg",
    )
    assert existing.genius_url == "https://genius.com/original"
    assert existing.cover_url == "https://x/original.jpg"


def test_merge_appends_the_new_category_label_when_different():
    existing = _report(category="audio")
    merge_into_existing_report(existing, category="lyrics", description="", genius_url="", cover_url="")
    assert "Lyrics broken" in existing.description


def test_merge_does_not_append_a_category_note_when_the_category_matches():
    existing = _report(category="audio")
    merge_into_existing_report(existing, category="audio", description="", genius_url="", cover_url="")
    assert existing.description == ""


def test_merge_appends_new_description_text():
    existing = _report(category="audio", description="cuts out at the start")
    merge_into_existing_report(
        existing, category="audio", description="also silent at the end", genius_url="", cover_url=""
    )
    assert "cuts out at the start" in existing.description
    assert "also silent at the end" in existing.description


def test_merge_appends_both_category_note_and_description():
    existing = _report(category="audio", description="cuts out")
    merge_into_existing_report(
        existing, category="video", description="also no video", genius_url="", cover_url=""
    )
    assert "cuts out" in existing.description
    assert "Missing video" in existing.description
    assert "also no video" in existing.description
