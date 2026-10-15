"""Tests for the "Save and admit" button on the admin edit form of a pending
request or report (app/routes/admin.py): it submits the edit form itself,
so the admin's unsaved inputs are saved first and then admitted. Inputs
that fail the edit form's own checks are not saved; the form comes back
with the inputs kept and the errors shown. When the inputs save fine but
the admit gate still refuses (a request whose song is already in the
library), the inputs stay saved and the form shows the error.
"""

from __future__ import annotations

from app.database import SessionLocal
from app.models import BrokenReport, PendingBrokenReport, PendingSongRequest, SongRequest

_MBID = "b10bbbfc-cf9e-42e0-be17-e2c3e1d2600d"
_REQUEST_FIELDS = {
    "band_name": "Journey", "song_name": "Faithfully",
    "youtube_url": "https://www.youtube.com/watch?v=x", "language": "en",
    "lyrics_url": "https://genius.com/journey-faithfully-lyrics", "musicbrainz_id": _MBID,
}
_FOLDER = "Queen - Bohemian Rhapsody"
_REPORT_FIELDS = {
    "song_folder": _FOLDER, "category": "audio", "description": "cuts out after the chorus",
    "language": "en", "genius_url": "https://genius.com/Queen-bohemian-rhapsody-lyrics",
}
_ADMIT = {"after_save": "admit"}


def _pending_request_id(admin_client, **overrides) -> int:
    admin_client.post("/request", data={"band_name": "Journey", "song_name": "Faithfully", **overrides})
    with SessionLocal() as db:
        return db.query(PendingSongRequest).one().id


def _pending_report_id(admin_client) -> int:
    admin_client.post(
        "/report", data={"song_folder": _FOLDER, "category": "audio", "description": "x", "language": "en"},
    )
    with SessionLocal() as db:
        return db.query(PendingBrokenReport).one().id


# ------------------------------------------------------------------ requests
def test_request_edit_form_has_save_and_admit_inside_the_form(admin_client):
    pid = _pending_request_id(admin_client)
    html = admin_client.get(f"/admin/requests/pending/{pid}/edit").text
    form = html.split(f'action="/admin/requests/pending/{pid}/edit"', 1)[1].split("</form>", 1)[0]
    assert 'name="after_save" value="admit"' in form
    assert f'action="/admin/requests/pending/{pid}/admit"' not in html


def test_request_save_and_admit_saves_the_new_inputs_then_admits(admin_client):
    pid = _pending_request_id(admin_client)
    r = admin_client.post(
        f"/admin/requests/pending/{pid}/edit", data={**_REQUEST_FIELDS, **_ADMIT}, follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/admin/requests"
    with SessionLocal() as db:
        assert db.query(PendingSongRequest).count() == 0
        assert db.query(SongRequest).one().musicbrainz_id == _MBID


def test_request_save_and_admit_with_a_missing_field_stays_on_the_form(admin_client):
    pid = _pending_request_id(admin_client)
    fields = {**_REQUEST_FIELDS, "musicbrainz_id": "", "song_name": "Faithfully (Live)"}
    r = admin_client.post(f"/admin/requests/pending/{pid}/edit", data={**fields, **_ADMIT})
    assert r.status_code == 422
    assert "MusicBrainz ID is required." in r.text
    assert 'value="Faithfully (Live)"' in r.text  # the inputs are kept on the form
    with SessionLocal() as db:
        assert db.query(SongRequest).count() == 0
        assert db.get(PendingSongRequest, pid) is not None


def test_request_save_and_admit_saves_even_when_the_admit_gate_refuses(admin_client):
    pid = _pending_request_id(admin_client, song_name="Bohemian Rhapsodyyy", band_name="Queen")
    fields = {**_REQUEST_FIELDS, "band_name": "Queen", "song_name": "Bohemian Rhapsody"}
    r = admin_client.post(f"/admin/requests/pending/{pid}/edit", data={**fields, **_ADMIT})
    assert r.status_code == 422
    assert "already in the library" in r.text.lower()
    assert f'action="/admin/requests/pending/{pid}/edit"' in r.text
    with SessionLocal() as db:
        item = db.get(PendingSongRequest, pid)
        assert item.song_name == "Bohemian Rhapsody"
        assert item.musicbrainz_id == _MBID
        assert db.query(SongRequest).count() == 0


def test_request_plain_save_still_does_not_admit(admin_client):
    pid = _pending_request_id(admin_client)
    r = admin_client.post(f"/admin/requests/pending/{pid}/edit", data=_REQUEST_FIELDS, follow_redirects=False)
    assert r.status_code == 303
    with SessionLocal() as db:
        assert db.query(SongRequest).count() == 0
        assert db.get(PendingSongRequest, pid).musicbrainz_id == _MBID


# ------------------------------------------------------------------- reports
def test_report_edit_form_has_save_and_admit_inside_the_form(admin_client):
    pid = _pending_report_id(admin_client)
    html = admin_client.get(f"/admin/reports/pending/{pid}/edit").text
    form = html.split(f'action="/admin/reports/pending/{pid}/edit"', 1)[1].split("</form>", 1)[0]
    assert 'name="after_save" value="admit"' in form
    assert f'action="/admin/reports/pending/{pid}/admit"' not in html


def test_report_save_and_admit_saves_the_new_inputs_then_admits(admin_client):
    pid = _pending_report_id(admin_client)
    r = admin_client.post(
        f"/admin/reports/pending/{pid}/edit", data={**_REPORT_FIELDS, **_ADMIT}, follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/admin/reports"
    with SessionLocal() as db:
        assert db.query(PendingBrokenReport).count() == 0
        admitted = db.query(BrokenReport).one()
        assert admitted.description == "cuts out after the chorus"
        assert admitted.genius_url == _REPORT_FIELDS["genius_url"]


def test_report_save_and_admit_with_a_missing_field_stays_on_the_form(admin_client):
    pid = _pending_report_id(admin_client)
    r = admin_client.post(
        f"/admin/reports/pending/{pid}/edit", data={**_REPORT_FIELDS, "genius_url": "", **_ADMIT},
    )
    assert r.status_code == 422
    assert "lyrics link" in r.text
    assert "cuts out after the chorus" in r.text  # the inputs are kept on the form
    with SessionLocal() as db:
        assert db.query(BrokenReport).count() == 0
        assert db.get(PendingBrokenReport, pid) is not None
