"""Tests for the admin-editable app settings singleton (app/app_settings.py,
app/models.py: AppSettings) - the karaoke-night/strict profile switches for
the request-song and report-broken forms, set via the admin Settings view
(app/routes/admin.py)."""

from __future__ import annotations

from app.app_settings import get_app_settings
from app.database import SessionLocal


def test_get_app_settings_creates_a_default_row_on_first_use(fresh_db):
    with SessionLocal() as db:
        settings = get_app_settings(db)
        assert settings.request_profile == "karaoke_night"
        assert settings.report_profile == "strict"


def test_get_app_settings_returns_the_same_row_on_later_calls(fresh_db):
    with SessionLocal() as db:
        first = get_app_settings(db)
        first.request_profile = "strict"
        db.commit()

    with SessionLocal() as db:
        second = get_app_settings(db)
        assert second.request_profile == "strict"


# ---------------------------------------------------------- admin settings view
def test_settings_view_requires_admin(client):
    r = client.get("/admin/settings", follow_redirects=False)
    assert r.status_code in (302, 303, 403)


def test_settings_view_shows_current_profiles(admin_client):
    r = admin_client.get("/admin/settings")
    assert r.status_code == 200
    assert "Karaoke night" in r.text
    assert "Strict" in r.text


def test_settings_view_updates_request_profile(admin_client):
    r = admin_client.post(
        "/admin/settings",
        data={"request_profile": "strict", "report_profile": "strict"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    with SessionLocal() as db:
        settings = get_app_settings(db)
        assert settings.request_profile == "strict"
        assert settings.report_profile == "strict"


def test_settings_view_updates_report_profile_independently(admin_client):
    admin_client.post(
        "/admin/settings",
        data={"request_profile": "karaoke_night", "report_profile": "karaoke_night"},
    )
    with SessionLocal() as db:
        settings = get_app_settings(db)
        assert settings.request_profile == "karaoke_night"
        assert settings.report_profile == "karaoke_night"


def test_settings_view_rejects_an_unknown_profile(admin_client):
    r = admin_client.post(
        "/admin/settings",
        data={"request_profile": "not-a-profile", "report_profile": "strict"},
    )
    assert r.status_code == 422


def test_settings_nav_link_shown_to_admin(admin_client):
    r = admin_client.get("/admin/reports")
    assert 'href="/admin/settings"' in r.text
