"""Tests for the admin broken-report edit form (pending and admitted) and its
Admit gate: both always require a language and a lyrics link, for every
category and independent of the report-form profile switch in Settings
(app/routes/admin.py: _ADMIN_REPORT_REQUIRED_FIELDS). The category rules
(description, or a cover link for "cover") still apply on top. The public
report form keeps following its profile (app/profiles.py).
"""

from __future__ import annotations

from app.database import SessionLocal
from app.models import BrokenReport, PendingBrokenReport

_FOLDER = "Queen - Bohemian Rhapsody"
_GENIUS = "https://genius.com/Queen-bohemian-rhapsody-lyrics"


def _set_profiles(admin_client, report_profile: str) -> None:
    admin_client.post(
        "/admin/settings",
        data={"request_profile": "karaoke_night", "report_profile": report_profile, "mode": "production"},
    )


def _pending_report(admin_client, **overrides) -> int:
    _set_profiles(admin_client, "karaoke_night")
    data = {"song_folder": _FOLDER, "category": "audio", "description": "cuts out"}
    data.update(overrides)
    admin_client.post("/report", data=data)
    with SessionLocal() as db:
        return db.query(PendingBrokenReport).one().id


def _admitted_report() -> int:
    with SessionLocal() as db:
        row = BrokenReport(song_folder=_FOLDER, category="audio", description="cuts out", reporter_username="admin")
        db.add(row)
        db.commit()
        return row.id


def test_edit_form_marks_language_and_lyrics_link_required(admin_client):
    pid = _pending_report(admin_client)
    r = admin_client.get(f"/admin/reports/pending/{pid}/edit")
    assert "Language <em>(required)</em>" in r.text
    assert "Lyrics link <em>(required)</em>" in r.text
    assert 'name="genius_url" required' in r.text
    # no category-driven JS hook that could switch the requirement off again
    assert "data-broken-genius" not in r.text


def test_pending_edit_save_rejected_without_lyrics_link_or_language(admin_client):
    pid = _pending_report(admin_client)
    r = admin_client.post(
        f"/admin/reports/pending/{pid}/edit",
        data={"song_folder": _FOLDER, "category": "audio", "description": "changed"},
    )
    assert r.status_code == 422
    assert "Please provide a genius.com or lrclib.net lyrics link." in r.text
    assert "Please choose the song" in r.text
    with SessionLocal() as db:
        assert db.get(PendingBrokenReport, pid).description == "cuts out"


def test_pending_edit_saves_once_complete(admin_client):
    pid = _pending_report(admin_client)
    r = admin_client.post(
        f"/admin/reports/pending/{pid}/edit",
        data={
            "song_folder": _FOLDER, "category": "audio", "description": "changed",
            "language": "en", "genius_url": _GENIUS,
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    with SessionLocal() as db:
        assert db.get(PendingBrokenReport, pid).genius_url == _GENIUS


def test_admitted_edit_save_rejected_without_lyrics_link(admin_client):
    rid = _admitted_report()
    r = admin_client.post(
        f"/admin/reports/{rid}/edit",
        data={"song_folder": _FOLDER, "category": "audio", "description": "changed", "language": "en"},
    )
    assert r.status_code == 422
    assert "Please provide a genius.com or lrclib.net lyrics link." in r.text
    with SessionLocal() as db:
        assert db.get(BrokenReport, rid).description == "cuts out"


def test_admit_requires_lyrics_link_for_every_category(admin_client):
    # "audio" never needed a lyrics link before, not even under strict.
    pid = _pending_report(admin_client, language="en")
    r = admin_client.post(f"/admin/reports/pending/{pid}/admit")
    assert r.status_code == 422
    assert "Please provide a genius.com or lrclib.net lyrics link." in r.text
    with SessionLocal() as db:
        assert db.query(BrokenReport).count() == 0


def test_admit_requires_language_even_under_karaoke_night(admin_client):
    pid = _pending_report(admin_client, genius_url=_GENIUS)
    r = admin_client.post(f"/admin/reports/pending/{pid}/admit")
    assert r.status_code == 422
    assert "Please choose the song" in r.text


def test_admit_succeeds_once_language_and_lyrics_link_are_set(admin_client):
    pid = _pending_report(admin_client, language="en", genius_url=_GENIUS)
    r = admin_client.post(f"/admin/reports/pending/{pid}/admit", follow_redirects=False)
    assert r.status_code == 303
    with SessionLocal() as db:
        assert db.query(BrokenReport).count() == 1


def test_category_rules_still_apply_on_the_admin_form(admin_client):
    pid = _pending_report(admin_client)
    base = {"song_folder": _FOLDER, "language": "en", "genius_url": _GENIUS}
    # "cover" needs a cover link, not a description
    r = admin_client.post(f"/admin/reports/pending/{pid}/edit", data={**base, "category": "cover"})
    assert r.status_code == 422
    assert "cover image link" in r.text
    r = admin_client.post(
        f"/admin/reports/pending/{pid}/edit",
        data={**base, "category": "cover", "cover_url": "https://example.com/c.jpg"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    # every other category needs a description
    r = admin_client.post(f"/admin/reports/pending/{pid}/edit", data={**base, "category": "audio"})
    assert r.status_code == 422
    assert "describe what" in r.text


def test_public_report_form_still_follows_its_profile(admin_client):
    _set_profiles(admin_client, "karaoke_night")
    r = admin_client.post("/report", data={"song_folder": _FOLDER, "category": "audio", "description": "x"})
    assert r.status_code == 200
    with SessionLocal() as db:
        assert db.query(PendingBrokenReport).count() == 1
