"""Tests for the Genre and Trait columns in the admin tables (pending and
admitted, on /admin/requests and /admin/reports): each cell shows the labels
of what the CSV export carries for the row, so a row nobody tagged yet reads
"Default" / "None" (app/genres.py, app/traits.py: genre_text()/trait_text()).
"""

from __future__ import annotations

import re

from app import genres, traits
from app.database import SessionLocal
from app.models import BrokenReport, PendingBrokenReport, PendingSongRequest, SongRequest

_FOLDER = "Queen - Bohemian Rhapsody"


def _headers(html: str, section_id: str) -> list[str]:
    section = html.split(f'id="{section_id}"', 1)[1]
    thead = section.split("<thead>", 1)[1].split("</thead>", 1)[0]
    return re.findall(r"<th>([^<]*)</th>", thead)


def _row_cells(html: str, marker: str) -> str:
    """The <tr> containing `marker`."""
    before, after = html.split(marker, 1)
    return before.rsplit("<tr", 1)[1] + marker + after.split("</tr>", 1)[0]


def test_genre_text_joins_labels():
    assert genres.genre_text("metal,gothic") == "Metal, Gothic"
    assert genres.genre_text(None) == "Default"
    assert genres.genre_text("unknown_code") == "unknown_code"


def test_trait_text_joins_labels():
    assert traits.trait_text("harsh_vocals,choir") == "Harsh vocals, Choir"
    assert traits.trait_text("") == "None"


def test_requests_tables_show_genre_and_trait(admin_client):
    with SessionLocal() as db:
        db.add(PendingSongRequest(band_name="Arkona", song_name="Goi", genre="metal,folk", trait="harsh_vocals",
                                  requester_username="admin"))
        db.add(SongRequest(band_name="Therion", song_name="Ginnungagap", genre=None, trait=None,
                           requester_username="admin"))
        db.commit()
    html = admin_client.get("/admin/requests?show=all").text

    for section in ("needs-review", "all-requests"):
        headers = _headers(html, section)
        assert "Genre" in headers and "Trait" in headers
    pending = _row_cells(html, "Arkona")
    assert "Metal, Folk" in pending and "Harsh vocals" in pending
    admitted = _row_cells(html, "Therion")
    assert "Default" in admitted and "None" in admitted


def test_reports_tables_show_genre_and_trait(admin_client):
    with SessionLocal() as db:
        db.add(PendingBrokenReport(song_folder=_FOLDER, category="audio", description="pending one",
                                   genre="gothic", trait="choir,operatic_vocals", reporter_username="admin"))
        db.add(BrokenReport(song_folder=_FOLDER, category="audio", description="admitted one",
                            reporter_username="admin"))
        db.commit()
    html = admin_client.get("/admin/reports?show=all").text

    for section in ("needs-review", "all-reports"):
        headers = _headers(html, section)
        assert "Genre" in headers and "Trait" in headers
    pending = _row_cells(html, "pending one")
    assert "Gothic" in pending and "Choir, Operatic vocals" in pending
    admitted = _row_cells(html, "admitted one")
    assert "Default" in admitted and "None" in admitted
