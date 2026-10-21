"""Tests for the public songs landing page (/songs): the "Reported broken"
badge on songs with a pending or open report (app/known_broken.py), shown to
everyone. The recently added/updated panels live on their own page
(tests/test_whats_new.py).
"""

from __future__ import annotations

import re

from app.database import SessionLocal
from app.models import BrokenReport, PendingBrokenReport

BADGE = '<span class="badge-broken" title="{title}">Reported broken</span>'


def _row_of(html: str, title: str) -> str:
    """The song-list <summary> row showing this title."""
    for row in re.findall(r'<summary class="song-row">.*?</summary>', html, re.S):
        if f'<span class="song-title">{title}</span>' in row:
            return row
    raise AssertionError(f"no row for {title}")


def test_a_song_with_a_pending_or_open_report_gets_the_badge_for_guests(client):
    with SessionLocal() as db:
        db.add(PendingBrokenReport(song_folder="Queen - Bohemian Rhapsody", category="lyrics", description="x",
                                   reporter_username="admin"))
        db.add(BrokenReport(song_folder="Toto - Africa", category="audio", description="x",
                            reporter_username="admin"))
        db.commit()
    html = client.get("/songs").text
    assert BADGE.format(title="Lyrics broken") in _row_of(html, "Bohemian Rhapsody")
    assert BADGE.format(title="Missing audio") in _row_of(html, "Africa")
    assert "badge-broken" not in _row_of(html, "Take On Me")


def test_a_resolved_report_shows_no_badge(client):
    with SessionLocal() as db:
        db.add(BrokenReport(song_folder="Toto - Africa", category="audio", description="x", status="resolved",
                            reporter_username="admin"))
        db.commit()
    assert "badge-broken" not in client.get("/songs").text


def test_the_live_search_results_carry_the_badge_too(client):
    with SessionLocal() as db:
        db.add(BrokenReport(song_folder="Toto - Africa", category=None, description="x",
                            reporter_username="admin"))
        db.commit()
    html = client.get("/songs/partial", params={"q": "africa"}).text
    assert BADGE.format(title="Reported broken") in _row_of(html, "Africa")


def test_the_songs_page_has_no_side_panels_and_links_to_whats_new(client):
    html = client.get("/songs").text
    assert "side-panel" not in html
    assert '<a href="/new"' in html
