"""Tests for the admin-only genre/trait fields on SongRequest and
BrokenReport (and their Pending* counterparts, app/models.py) - introduced
when an admin reviews a request/report, not on the public forms. See
app/genres.py, app/traits.py. Both default to "default"/"none" and are
always present in the CSV exports (app/routes/admin.py: requests_csv,
reports_csv).
"""

from __future__ import annotations

from app.database import SessionLocal
from app.models import BrokenReport, PendingBrokenReport, PendingSongRequest, SongRequest


def test_new_song_request_defaults_genre_and_trait(fresh_db):
    with SessionLocal() as db:
        db.add(SongRequest(band_name="Journey", song_name="Faithfully", requester_username="admin"))
        db.commit()
        row = db.query(SongRequest).one()
        assert row.genre == "default"
        assert row.trait == "none"


def test_new_broken_report_defaults_genre_and_trait(fresh_db):
    with SessionLocal() as db:
        db.add(
            BrokenReport(
                song_folder="Queen - Bohemian Rhapsody", category="audio",
                description="x", reporter_username="admin",
            )
        )
        db.commit()
        row = db.query(BrokenReport).one()
        assert row.genre == "default"
        assert row.trait == "none"


# ---------------------------------------------------------------- public forms
def test_genre_and_trait_not_shown_on_public_request_form(admin_client):
    r = admin_client.get("/request")
    assert 'name="genre"' not in r.text
    assert 'name="trait"' not in r.text


def test_genre_and_trait_not_shown_on_public_report_form(admin_client):
    r = admin_client.get("/report")
    assert 'name="genre"' not in r.text
    assert 'name="trait"' not in r.text


# --------------------------------------------------------- admin edit: request
def _submit_request(admin_client, **overrides):
    data = {"band_name": "Journey", "song_name": "Faithfully"}
    data.update(overrides)
    admin_client.post("/request", data=data)


def _pending_request_id() -> int:
    with SessionLocal() as db:
        return db.query(PendingSongRequest).one().id


def test_admin_can_edit_genre_and_trait_on_a_pending_request(admin_client):
    _submit_request(admin_client)
    pid = _pending_request_id()
    r = admin_client.get(f"/admin/requests/pending/{pid}/edit")
    assert 'name="genre"' in r.text
    assert 'name="trait"' in r.text

    admin_client.post(
        f"/admin/requests/pending/{pid}/edit",
        data={
            "band_name": "Journey", "song_name": "Faithfully",
            "genre": ["metal", "gothic"], "trait": "harsh_vocals",
        },
    )
    with SessionLocal() as db:
        row = db.query(PendingSongRequest).one()
        assert row.genre == "metal,gothic"
        assert row.trait == "harsh_vocals"


def test_genre_and_trait_carry_over_on_admit(admin_client):
    _submit_request(admin_client)
    pid = _pending_request_id()
    admin_client.post(
        f"/admin/requests/pending/{pid}/edit",
        data={
            "band_name": "Journey", "song_name": "Faithfully",
            "youtube_url": "https://www.youtube.com/watch?v=x",
            "language": "en", "lyrics_url": "https://genius.com/journey-faithfully-lyrics",
            "genre": ["metal"], "trait": "choir",
        },
    )
    admin_client.post(f"/admin/requests/pending/{pid}/admit")
    with SessionLocal() as db:
        admitted = db.query(SongRequest).one()
        assert admitted.genre == "metal"
        assert admitted.trait == "choir"


def test_admin_can_edit_genre_and_trait_on_an_admitted_request(admin_client):
    with SessionLocal() as db:
        db.add(SongRequest(band_name="Journey", song_name="Faithfully", requester_username="admin"))
        db.commit()
        rid = db.query(SongRequest).one().id

    admin_client.post(
        f"/admin/requests/{rid}/edit",
        data={"band_name": "Journey", "song_name": "Faithfully", "genre": ["pop"], "trait": "none"},
    )
    with SessionLocal() as db:
        assert db.get(SongRequest, rid).genre == "pop"


# ---------------------------------------------------------- admin edit: report
def _pending_report_id() -> int:
    with SessionLocal() as db:
        return db.query(PendingBrokenReport).one().id


def test_admin_can_edit_genre_and_trait_on_a_pending_report(admin_client):
    admin_client.post(
        "/report",
        data={
            "song_folder": "Queen - Bohemian Rhapsody", "category": "audio",
            "description": "no audio", "language": "de",
        },
    )
    pid = _pending_report_id()
    r = admin_client.get(f"/admin/reports/pending/{pid}/edit")
    assert 'name="genre"' in r.text
    assert 'name="trait"' in r.text

    admin_client.post(
        f"/admin/reports/pending/{pid}/edit",
        data={
            "song_folder": "Queen - Bohemian Rhapsody", "category": "audio",
            "description": "no audio", "language": "de",
            "genre": ["symphonic"], "trait": "operatic_vocals",
        },
    )
    with SessionLocal() as db:
        row = db.query(PendingBrokenReport).one()
        assert row.genre == "symphonic"
        assert row.trait == "operatic_vocals"


def test_genre_and_trait_carry_over_on_report_admit(admin_client):
    admin_client.post(
        "/report",
        data={
            "song_folder": "Queen - Bohemian Rhapsody", "category": "audio",
            "description": "no audio", "language": "de",
        },
    )
    pid = _pending_report_id()
    admin_client.post(
        f"/admin/reports/pending/{pid}/edit",
        data={
            "song_folder": "Queen - Bohemian Rhapsody", "category": "audio",
            "description": "no audio", "language": "de",
            "genre": ["symphonic"], "trait": "operatic_vocals",
        },
    )
    admin_client.post(f"/admin/reports/pending/{pid}/admit")
    with SessionLocal() as db:
        admitted = db.query(BrokenReport).one()
        assert admitted.genre == "symphonic"
        assert admitted.trait == "operatic_vocals"


# --------------------------------------------------------------------- exports
def test_requests_csv_includes_genre_and_trait_columns(admin_client):
    with SessionLocal() as db:
        db.add(
            SongRequest(
                band_name="Journey", song_name="Faithfully", requester_username="admin",
                genre="metal,gothic", trait="choir",
            )
        )
        db.commit()
    body = admin_client.get("/admin/requests.csv").text
    assert body.startswith(
        "band name,song name,youtube link,language,musicbrainz_id,lyrics_url,cover_url,duet,genre,trait\n"
    )
    assert 'Journey,Faithfully,,,,,,,"metal,gothic",choir\n' in body


def test_reports_csv_includes_genre_and_trait_columns(admin_client):
    with SessionLocal() as db:
        db.add(
            BrokenReport(
                song_folder="Queen - Bohemian Rhapsody", category="audio", description="x",
                reporter_username="admin", genre="symphonic", trait="operatic_vocals",
            )
        )
        db.commit()
    body = admin_client.get("/admin/reports.csv").text
    assert body.startswith(
        "band,song name,category,description,lyrics_url,language,cover_url,genre,trait\n"
    )
    assert body.splitlines()[1].endswith(",symphonic,operatic_vocals")
