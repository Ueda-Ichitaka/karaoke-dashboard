"""Tests for the "Reported broken" badge mode on the admin Settings page
(app/broken_badge.py, AppSettings.broken_badge): "until resolved" keeps the
badge until an admin resolves the report; "until updated" also drops it
once the library scan recorded a write to the song's files after the report
was drafted. It only affects the public song list and the "What's new"
page, never the admin report lists.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.app_settings import get_app_settings
from app.database import SessionLocal
from app.models import BrokenReport, LibraryFolder

FOLDER = "Toto - Africa"
REPORTED = datetime.now(UTC) - timedelta(days=10)
BADGE = 'class="badge-broken"'


def _save(admin_client, **overrides):
    data = {"request_profile": "karaoke_night", "report_profile": "strict", "mode": "production",
            "logging_enabled": "on", **overrides}
    return admin_client.post("/admin/settings", data=data, follow_redirects=False)


def _reported_then_updated() -> None:
    with SessionLocal() as db:
        db.add(BrokenReport(song_folder=FOLDER, category="audio", description="x", reporter_username="admin",
                            created_at=REPORTED))
        db.add(LibraryFolder(folder=FOLDER, first_seen_at=REPORTED - timedelta(days=1), follows_convention=True,
                             files="{}", updated_at=REPORTED + timedelta(days=2)))
        db.commit()


def test_the_default_is_until_resolved(fresh_db):
    with SessionLocal() as db:
        assert get_app_settings(db).broken_badge == "until_resolved"


def test_the_settings_page_offers_both_modes(admin_client):
    html = admin_client.get("/admin/settings").text
    assert '<select name="broken_badge">' in html
    assert '<option value="until_resolved" selected>' in html
    assert '<option value="until_updated" >' in html


def test_saving_switches_the_mode(admin_client):
    assert _save(admin_client, broken_badge="until_updated").status_code == 303
    with SessionLocal() as db:
        assert get_app_settings(db).broken_badge == "until_updated"


def test_an_unknown_mode_is_rejected(admin_client):
    assert _save(admin_client, broken_badge="never").status_code == 422


def test_saving_without_the_field_keeps_the_mode(admin_client):
    _save(admin_client, broken_badge="until_updated")
    _save(admin_client)
    with SessionLocal() as db:
        assert get_app_settings(db).broken_badge == "until_updated"


def test_until_resolved_keeps_the_badge_after_an_update(admin_client):
    _reported_then_updated()
    assert BADGE in admin_client.get("/songs", params={"q": "africa"}).text
    assert BADGE in admin_client.get("/new").text


def test_until_updated_drops_the_badge_on_the_public_pages_only(admin_client):
    _reported_then_updated()
    _save(admin_client, broken_badge="until_updated")
    assert BADGE not in admin_client.get("/songs", params={"q": "africa"}).text
    assert BADGE not in admin_client.get("/songs/partial", params={"q": "africa"}).text
    assert BADGE not in admin_client.get("/new").text
    assert BADGE not in admin_client.get("/new/partial").text
    reports = admin_client.get("/admin/reports").text
    assert f'<span class="mono">{FOLDER}</span>' in reports
    assert "Updated since report" in reports
