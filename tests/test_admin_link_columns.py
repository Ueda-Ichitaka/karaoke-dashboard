"""Tests for the link columns (YouTube, Lyrics, Cover) in the admin tables on
/admin/requests and /admin/reports: they only show a short "link", so they
use the narrow link-cell class instead of the wide free-text "wrap" class
(app/static/style.css), which reserves room the description column needs.
"""

from __future__ import annotations

import re

from app.database import SessionLocal
from app.models import BrokenReport, PendingBrokenReport, PendingSongRequest, SongRequest

_URL = "https://example.com/x"


def _cells_with_links(html: str) -> list[str]:
    """The opening <td ...> tag of every cell holding a link."""
    return re.findall(r'(<td[^>]*>)\s*(?:\{[^}]*\}\s*)?<a href="https://example\.com/x"', html)


def test_request_link_cells_are_narrow(admin_client):
    with SessionLocal() as db:
        for model in (PendingSongRequest, SongRequest):
            db.add(model(band_name="Journey", song_name="Faithfully", youtube_url=_URL, lyrics_url=_URL,
                         cover_url=_URL, requester_username="admin"))
        db.commit()
    cells = _cells_with_links(admin_client.get("/admin/requests").text)
    assert len(cells) == 6
    assert all(cell == '<td class="link-cell">' for cell in cells)


def test_report_link_cells_are_narrow(admin_client):
    with SessionLocal() as db:
        for model in (PendingBrokenReport, BrokenReport):
            db.add(model(song_folder="Queen - Bohemian Rhapsody", category="audio", description="x",
                         genius_url=_URL, cover_url=_URL, reporter_username="admin"))
        db.commit()
    html = admin_client.get("/admin/reports").text
    cells = _cells_with_links(html)
    assert len(cells) == 4
    assert all(cell == '<td class="link-cell">' for cell in cells)
    assert '<td class="wrap">x</td>' in html  # the description keeps its room
