"""Tests for the public "What's new" page (/new): the "Recently added" and
"Recently updated" panels side by side - the songs the library scan
(app/library_history.py) recorded as new or written in the last 2 months -
with a search bar on top that narrows both (live via /new/partial), and the
"Reported broken" badge on their entries. On a narrow screen the panels
stack.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from app import songs as song_index
from app.database import SessionLocal
from app.models import BrokenReport, LibraryFolder

BADGE = '<span class="badge-broken" title="{title}">Reported broken</span>'


def _record(added: dict[str, int] | None = None, updated: dict[str, int] | None = None,
            convention: dict[str, bool] | None = None) -> None:
    """Records every library folder as the library scan would: first seen a
    year ago and never updated, except the given ones (days ago)."""
    now = datetime.now(UTC)
    added, updated, convention = added or {}, updated or {}, convention or {}
    with SessionLocal() as db:
        for song in song_index.all_songs():
            db.add(LibraryFolder(
                folder=song.folder, first_seen_at=now - timedelta(days=added.get(song.folder, 365)),
                follows_convention=convention.get(song.folder, True), files="{}",
                updated_at=now - timedelta(days=updated[song.folder]) if song.folder in updated else None,
            ))
        db.commit()


def _panel(html: str, panel_id: str) -> str:
    match = re.search(rf'<section class="side-panel" id="{panel_id}".*?</section>', html, re.S)
    assert match, f"no {panel_id} panel"
    return match.group(0)


def _added(html: str) -> str:
    return _panel(html, "recent-additions")


def _updated(html: str) -> str:
    return _panel(html, "recent-updates")


def test_recently_added_lists_songs_first_seen_in_the_last_two_months_newest_first(client):
    _record(added={"Queen - Bohemian Rhapsody": 0, "Toto - Africa": 50, "ABBA - Dancing Queen": 70})
    recent = _added(client.get("/new").text)
    assert recent.index("Bohemian Rhapsody") < recent.index("Africa")
    assert "Dancing Queen" not in recent
    assert "Take On Me" not in recent
    added = (datetime.now(UTC) - timedelta(days=50)).strftime("%Y-%m-%d")
    assert f'<time datetime="{added}">{added}</time>' in recent
    assert 'href="/songs?q=Toto%20-%20Africa"' in recent


def test_recently_added_leaves_out_folders_breaking_the_convention(client):
    _record(added={"Toto - Africa": 1, "PlainFolderNoSeparator": 1}, convention={"PlainFolderNoSeparator": False})
    recent = _added(client.get("/new").text)
    assert "Africa" in recent
    assert "PlainFolderNoSeparator" not in recent


def test_recently_updated_lists_songs_written_in_the_last_two_months_newest_first(client):
    _record(updated={"Queen - Bohemian Rhapsody": 1, "Toto - Africa": 20, "ABBA - Dancing Queen": 70})
    recent = _updated(client.get("/new").text)
    assert recent.index("Bohemian Rhapsody") < recent.index("Africa")
    assert "Dancing Queen" not in recent
    updated = (datetime.now(UTC) - timedelta(days=20)).strftime("%Y-%m-%d")
    assert f'<time datetime="{updated}">{updated}</time>' in recent
    assert 'href="/songs?q=Toto%20-%20Africa"' in recent
    assert "Africa" not in _added(client.get("/new").text)


def test_both_lists_carry_the_badge(client):
    _record(added={"Toto - Africa": 3}, updated={"Toto - Africa": 1})
    with SessionLocal() as db:
        db.add(BrokenReport(song_folder="Toto - Africa", category="audio", description="x",
                            reporter_username="admin"))
        db.commit()
    html = client.get("/new").text
    assert BADGE.format(title="Missing audio") in _added(html)
    assert BADGE.format(title="Missing audio") in _updated(html)


def test_the_search_narrows_both_lists(client):
    _record(added={"Toto - Africa": 3, "Queen - Bohemian Rhapsody": 3},
            updated={"Toto - Africa": 1, "Queen - Bohemian Rhapsody": 1})
    html = client.get("/new", params={"q": "africa"}).text
    for panel in (_added(html), _updated(html)):
        assert "Africa" in panel
        assert "Bohemian Rhapsody" not in panel
    assert 'value="africa"' in html
    assert "No songs added in the last 2 months matching" not in html


def test_a_search_without_matches_says_so(client):
    _record(added={"Toto - Africa": 3})
    html = client.get("/new", params={"q": "zzz"}).text
    assert 'No songs added in the last 2 months matching "zzz".' in _added(html)
    assert 'No songs updated in the last 2 months matching "zzz".' in _updated(html)


def test_the_search_is_live_through_a_partial_with_both_panels(client):
    _record(added={"Toto - Africa": 3, "Queen - Bohemian Rhapsody": 3})
    html = client.get("/new").text
    assert 'data-live-search data-target="#new-results" data-endpoint="/new/partial"' in html
    partial = client.get("/new/partial", params={"q": "africa"}).text
    assert "<html" not in partial.lower()
    assert "Africa" in _added(partial)
    assert "Bohemian Rhapsody" not in _added(partial)
    assert 'id="recent-updates"' in partial


def test_both_lists_say_so_when_empty(client):
    html = client.get("/new").text
    assert "No songs added in the last 2 months." in _added(html)
    assert "No songs updated in the last 2 months." in _updated(html)


def test_the_page_puts_the_search_above_both_panels_side_by_side(client):
    html = client.get("/new").text
    assert (html.index('<form class="search" method="get" action="/new"') < html.index('<div id="new-results"')
            < html.index('<div class="new-panels">') < html.index('id="recent-additions"')
            < html.index('id="recent-updates"'))


def test_the_page_has_its_own_tab_next_to_songs(client):
    html = client.get("/new").text
    assert '<a href="/new" class="active">What\'s new</a>' in html
    assert html.index('<a href="/songs"') < html.index('<a href="/new"') < html.index('<a href="/report"')


def test_visiting_the_page_records_nothing(client):
    client.get("/new")
    with SessionLocal() as db:
        assert db.query(LibraryFolder).count() == 0  # only the library scan records folders
