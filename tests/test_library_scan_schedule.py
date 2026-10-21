"""Tests for the library scan schedule on the admin Settings page
(AppSettings.library_scan_cron): a standard cron expression, checked on
save, that takes effect at once - the running scheduler's "library-scan"
job is rescheduled - and is used again at the next app start. Also the
"Settings saved." confirmation after saving.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.app_settings import get_app_settings
from app.database import SessionLocal
from app.main import app


def _save(admin_client, **overrides):
    data = {"request_profile": "karaoke_night", "report_profile": "strict", "mode": "production",
            "logging_enabled": "on", **overrides}
    return admin_client.post("/admin/settings", data=data, follow_redirects=False)


def _stored() -> str:
    with SessionLocal() as db:
        return get_app_settings(db).library_scan_cron


def _running_trigger() -> tuple[str, str, str]:
    fields = {f.name: str(f) for f in app.state.scheduler.get_job("library-scan").trigger.fields}
    return fields["minute"], fields["hour"], fields["day_of_week"]


def test_the_default_schedule_is_daily_at_11(admin_client):
    assert _stored() == "0 11 * * *"
    assert 'name="library_scan_cron" value="0 11 * * *"' in admin_client.get("/admin/settings").text


def test_saving_a_schedule_stores_it_and_reschedules_the_running_scan(admin_client):
    assert _save(admin_client, library_scan_cron="  */30   6-22 * * mon-fri ").status_code == 303
    assert _stored() == "*/30 6-22 * * mon-fri"
    assert _running_trigger() == ("*/30", "6-22", "mon-fri")


def test_an_invalid_schedule_is_refused_and_nothing_changes(admin_client):
    r = _save(admin_client, library_scan_cron="every day at 11", mode="debug")
    assert r.status_code == 422
    assert "Invalid library scan schedule" in r.text
    assert _stored() == "0 11 * * *"
    assert _running_trigger() == ("0", "11", "*")
    with SessionLocal() as db:
        assert get_app_settings(db).mode == "production"


def test_saving_without_the_field_keeps_the_schedule(admin_client):
    _save(admin_client, library_scan_cron="15 3 * * *")
    _save(admin_client)
    assert _stored() == "15 3 * * *"


def test_the_app_starts_with_the_saved_schedule(admin_client):
    _save(admin_client, library_scan_cron="15 3 * * *")
    with TestClient(app):
        assert _running_trigger() == ("15", "3", "*")


def test_saving_confirms_it(admin_client):
    r = _save(admin_client)
    assert r.headers["location"] == "/admin/settings?saved=1"
    assert '<div class="alert alert-ok">Settings saved.</div>' in admin_client.get(r.headers["location"]).text
    assert "Settings saved." not in admin_client.get("/admin/settings").text
