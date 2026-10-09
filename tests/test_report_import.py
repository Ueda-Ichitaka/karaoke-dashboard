"""Tests for importing broken-song reports from a CSV in the existing
broken.csv export format (app/report_import.py, POST /admin/reports/import).
Each usable row becomes a *pending* report (Needs review) - or merges into
an existing open/pending report for the same song, the same way a second
report from the public form does. Rows that can't be used are skipped and
listed with the reason; the rest still import.
"""

from __future__ import annotations

from app.database import SessionLocal
from app.models import BrokenReport, PendingBrokenReport

HEADER = "band,song name,category,description,lyrics_url,language,cover_url,genre,trait\n"
GENIUS = "https://genius.com/Queen-bohemian-rhapsody-lyrics"


def _import(admin_client, text: str | bytes, filename: str = "broken.csv"):
    body = text.encode("utf-8") if isinstance(text, str) else text
    return admin_client.post(
        "/admin/reports/import", files={"file": (filename, body, "text/csv")},
    )


def _pending() -> list[PendingBrokenReport]:
    with SessionLocal() as db:
        return db.query(PendingBrokenReport).order_by(PendingBrokenReport.id).all()


def test_import_page_is_linked_from_reports_and_admin_only(admin_client):
    assert "/admin/reports/import" in admin_client.get("/admin/reports").text
    assert admin_client.get("/admin/reports/import").status_code == 200

    admin_client.post("/admin/users", data={"username": "gus", "password": "gusgusgusgus"})
    admin_client.post("/logout")
    admin_client.post("/login", data={"username": "gus", "password": "gusgusgusgus"}, follow_redirects=False)
    assert admin_client.get("/admin/reports/import").status_code == 403
    assert _import(admin_client, HEADER).status_code == 403


def test_imports_a_row_with_every_field_as_a_pending_report(admin_client):
    csv_text = HEADER + (
        f'Queen,Bohemian Rhapsody,other,needs re-timing,{GENIUS},en,'
        f'https://example.com/c.jpg,"metal,rock","harsh_vocals,choir"\n'
    )
    r = _import(admin_client, csv_text)
    assert r.status_code == 200
    assert "1 imported" in r.text

    [row] = _pending()
    assert row.song_folder == "Queen - Bohemian Rhapsody"
    assert row.category == "other"
    assert row.description == "needs re-timing"
    assert row.genius_url == GENIUS
    assert row.language == "en"
    assert row.cover_url == "https://example.com/c.jpg"
    assert row.genre == "metal,rock"
    assert row.trait == "harsh_vocals,choir"
    assert row.reporter_username == "admin"
    with SessionLocal() as db:
        assert db.query(BrokenReport).count() == 0  # never straight into the exportable list


def test_blank_optional_columns_and_missing_trailing_columns_are_fine(admin_client):
    # an older export without language/cover_url/genre/trait columns
    r = _import(
        admin_client, "band,song name,category,description,lyrics_url\nQueen,Bohemian Rhapsody,audio,no audio,\n",
    )
    assert r.status_code == 200
    [row] = _pending()
    assert row.genius_url is None
    assert row.language is None
    assert row.genre == "default"
    assert row.trait == "none"


def test_file_without_a_header_row_is_read_positionally(admin_client):
    _import(admin_client, "Queen,Bohemian Rhapsody,audio,no audio,,de,,default,none\n")
    [row] = _pending()
    assert row.language == "de"


def test_utf8_bom_and_cp1252_files_are_decoded(admin_client):
    _import(admin_client, "﻿" + HEADER + "Queen,Bohemian Rhapsody,audio,Störung,,,,,\n")
    assert _pending()[0].description == "Störung"
    with SessionLocal() as db:
        db.query(PendingBrokenReport).delete()
        db.commit()
    _import(admin_client, (HEADER + "Queen,Bohemian Rhapsody,audio,Störung,,,,,\n").encode("cp1252"))
    assert _pending()[0].description == "Störung"


def test_folder_is_resolved_by_exact_band_dash_song_name_case_insensitively(admin_client):
    _import(admin_client, HEADER + "queen,bohemian rhapsody,audio,x,,,,,\n")
    assert _pending()[0].song_folder == "Queen - Bohemian Rhapsody"


def test_unusable_rows_are_skipped_with_a_reason_and_the_rest_still_imports(admin_client):
    csv_text = HEADER + (
        "Nobody,Unknown Song,audio,x,,,,,\n"
        "Queen,Bohemian Rhapsody,not-a-category,x,,,,,\n"
        "Queen,Bohemian Rhapsody,audio,x,,zz,,,\n"
        "Queen,Bohemian Rhapsody,audio,x,not-a-link,,,,\n"
        "Queen,Bohemian Rhapsody,audio,x,,,ftp://c.jpg,,\n"
        "Queen,Bohemian Rhapsody,audio,x,,,,not-a-genre,\n"
        "Queen,Bohemian Rhapsody,audio,x,,,,,not-a-trait\n"
        "Testband,Solo Song,video,no video,,,,,\n"
    )
    r = _import(admin_client, csv_text)
    assert r.status_code == 200
    assert "1 imported" in r.text
    assert "7 skipped" in r.text
    for reason in (
        "No library folder", "Unrecognized category", "Unrecognized language",
        "lyrics link must start with http", "cover image link must start with http",
        "Unrecognized genre", "Unrecognized trait",
    ):
        assert reason in r.text
    assert [p.song_folder for p in _pending()] == ["Testband - Solo Song"]


def test_row_for_a_song_with_a_pending_report_merges_into_it(admin_client):
    admin_client.post(
        "/report", data={"song_folder": "Queen - Bohemian Rhapsody", "category": "audio",
                         "description": "cuts out", "language": "en"},
    )
    r = _import(admin_client, HEADER + f"Queen,Bohemian Rhapsody,other,needs re-timing,{GENIUS},,,,\n")
    assert "1 merged" in r.text
    [row] = _pending()
    assert row.description == "cuts out; Other; needs re-timing"
    assert row.genius_url == GENIUS


def test_two_rows_for_the_same_song_in_one_file_become_one_report(admin_client):
    _import(
        admin_client,
        HEADER + "Queen,Bohemian Rhapsody,audio,first,,,,,\nQueen,Bohemian Rhapsody,audio,second,,,,,\n",
    )
    [row] = _pending()
    assert row.description == "first; second"


def test_round_trip_export_then_import_keeps_every_field(admin_client):
    with SessionLocal() as db:
        db.add(BrokenReport(
            song_folder="Queen - Bohemian Rhapsody", song_artist="Queen", song_title="Bohemian Rhapsody",
            category="lyrics", description="second verse wrong", genius_url=GENIUS, language="en",
            cover_url="https://example.com/c.jpg", genre="metal,gothic", trait="choir",
            reporter_username="admin",
        ))
        db.commit()
    exported = admin_client.get("/admin/reports.csv").content
    with SessionLocal() as db:
        db.query(BrokenReport).delete()
        db.commit()

    _import(admin_client, exported)
    [row] = _pending()
    assert (row.song_folder, row.category, row.description, row.genius_url, row.language,
            row.cover_url, row.genre, row.trait) == (
        "Queen - Bohemian Rhapsody", "lyrics", "second verse wrong", GENIUS, "en",
        "https://example.com/c.jpg", "metal,gothic", "choir",
    )


def test_empty_file_imports_nothing(admin_client):
    r = _import(admin_client, "")
    assert r.status_code == 200
    assert "0 imported" in r.text
    assert _pending() == []
