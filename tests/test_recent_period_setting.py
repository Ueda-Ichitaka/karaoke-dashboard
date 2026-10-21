"""Tests for the "What's new period" on the admin Settings page
(AppSettings.recent_amount/recent_unit, app/recent_period.py): how far back
the "Recently added" and "Recently updated" lists on /new reach - a whole
number of days, weeks or months, 2 months by default.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.app_settings import get_app_settings
from app.database import SessionLocal
from app.models import LibraryFolder


def _save(admin_client, **overrides):
    data = {"request_profile": "karaoke_night", "report_profile": "strict", "mode": "production",
            "logging_enabled": "on", **overrides}
    return admin_client.post("/admin/settings", data=data, follow_redirects=False)


def _stored() -> tuple[int, str]:
    with SessionLocal() as db:
        app_settings = get_app_settings(db)
        return app_settings.recent_amount, app_settings.recent_unit


def _added(days_ago_by_folder: dict[str, int]) -> None:
    now = datetime.now(UTC)
    with SessionLocal() as db:
        for folder, days in days_ago_by_folder.items():
            db.add(LibraryFolder(folder=folder, first_seen_at=now - timedelta(days=days), follows_convention=True,
                                 files="{}"))
        db.commit()


def test_the_default_is_two_months(admin_client):
    assert _stored() == (2, "months")
    html = admin_client.get("/admin/settings").text
    assert 'name="recent_amount" value="2"' in html
    assert '<option value="months" selected>Months</option>' in html
    assert "Last 2 months" in admin_client.get("/new").text


def test_saving_a_period_changes_how_far_back_the_lists_reach(admin_client):
    _added({"Toto - Africa": 10, "Queen - Bohemian Rhapsody": 25})
    assert "Bohemian Rhapsody" in admin_client.get("/new").text

    assert _save(admin_client, recent_amount=" 3 ", recent_unit="weeks").status_code == 303
    assert _stored() == (3, "weeks")
    html = admin_client.get("/new").text
    assert "Last 3 weeks" in html
    assert "Africa" in html
    assert "Bohemian Rhapsody" not in html
    assert "No songs updated in the last 3 weeks." in html


def test_one_unit_reads_in_the_singular(admin_client):
    _save(admin_client, recent_amount="1", recent_unit="weeks")
    assert "Last 1 week<" in admin_client.get("/new").text


@pytest.mark.parametrize(("amount", "unit"), [("0", "days"), ("1000", "days"), ("abc", "days"), ("", "days"),
                                              ("1.5", "weeks"), ("2", "hours")])
def test_an_invalid_period_is_refused_and_nothing_changes(admin_client, amount, unit):
    r = _save(admin_client, recent_amount=amount, recent_unit=unit, mode="debug")
    assert r.status_code == 422
    assert "<li>The What&#39;s new period must be" in r.text
    assert _stored() == (2, "months")


def test_saving_without_the_fields_keeps_the_period(admin_client):
    _save(admin_client, recent_amount="10", recent_unit="days")
    _save(admin_client)
    assert _stored() == (10, "days")
