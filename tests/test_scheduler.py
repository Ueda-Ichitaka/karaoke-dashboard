"""Tests for app/scheduler.py: the automatic monthly rescan of the
(expensive) duplicates report - see app/duplicates.py and its "Rescan"
button for the on-demand equivalent - and the library scan behind the
"Recently added"/"Recently updated" lists (app/library_history.py), which
runs on the schedule saved on the Settings page (standard cron, so weekday
0 and 7 are Sunday) and once at app start.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from apscheduler.triggers.date import DateTrigger

from app import duplicates, library_history
from app.config import Settings, settings
from app.library_history import DEFAULT_LIBRARY_SCAN_CRON
from app.scheduler import create_scheduler, cron_trigger, reschedule_library_scan


def _job(job_id: str, library_scan_cron: str = DEFAULT_LIBRARY_SCAN_CRON):
    return create_scheduler(library_scan_cron).get_job(job_id)


def _fields(job) -> dict[str, str]:
    return {f.name: str(f) for f in job.trigger.fields}


def test_the_duplicates_rescan_matches_the_configured_schedule():
    job = _job("duplicates-rescan")
    assert job.func is duplicates.refresh_cache
    fields = _fields(job)
    assert fields["day"] == str(settings.duplicates_rescan_day)
    assert fields["hour"] == str(settings.duplicates_rescan_hour)
    assert fields["minute"] == str(settings.duplicates_rescan_minute)


def test_the_library_scan_runs_daily_at_11_by_default():
    assert DEFAULT_LIBRARY_SCAN_CRON == "0 11 * * *"
    job = _job("library-scan")
    assert job.func is library_history.run_scan
    fields = _fields(job)
    assert (fields["minute"], fields["hour"], fields["day"], fields["day_of_week"]) == ("0", "11", "*", "*")


def test_the_library_scan_follows_the_cron_expression():
    fields = _fields(_job("library-scan", "*/30 6-22 * * mon-fri"))
    assert (fields["minute"], fields["hour"], fields["day_of_week"]) == ("*/30", "6-22", "mon-fri")


def test_an_invalid_stored_expression_falls_back_to_the_default():
    fields = _fields(_job("library-scan", "every day"))
    assert (fields["minute"], fields["hour"]) == ("0", "11")


def test_rescheduling_changes_the_library_scan_trigger():
    scheduler = create_scheduler(DEFAULT_LIBRARY_SCAN_CRON)
    reschedule_library_scan(scheduler, "15 3 * * *")
    fields = _fields(scheduler.get_job("library-scan"))
    assert (fields["minute"], fields["hour"]) == ("15", "3")


def test_an_invalid_expression_is_refused():
    with pytest.raises(ValueError):
        cron_trigger("every day")


def _weekdays(day_of_week: str) -> set[str]:
    """The weekdays a "0 11 * * <day_of_week>" schedule fires on, over two weeks."""
    trigger = cron_trigger(f"0 11 * * {day_of_week}")
    moment, days = datetime(2026, 10, 18, tzinfo=UTC), set()  # a Sunday
    while (moment := trigger.get_next_fire_time(None, moment + timedelta(minutes=1))) < datetime(
            2026, 11, 1, tzinfo=UTC):
        days.add(moment.strftime("%a"))
    return days


@pytest.mark.parametrize(("day_of_week", "expected"), [
    ("0", {"Sun"}),
    ("7", {"Sun"}),
    ("1", {"Mon"}),
    ("1-5", {"Mon", "Tue", "Wed", "Thu", "Fri"}),
    ("0,6", {"Sat", "Sun"}),
    ("5-7", {"Fri", "Sat", "Sun"}),
    ("*/2", {"Sun", "Tue", "Thu", "Sat"}),
    ("1-5/2", {"Mon", "Wed", "Fri"}),
    ("sat,sun", {"Sat", "Sun"}),
    ("*", {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}),
])
def test_weekday_numbers_follow_standard_cron(day_of_week, expected):
    assert _weekdays(day_of_week) == expected


def test_the_library_scan_also_runs_once_at_start(monkeypatch):
    assert Settings.model_fields["library_scan_on_start"].default is True
    monkeypatch.setattr(settings, "library_scan_on_start", True)
    job = _job("library-scan-start")
    assert job.func is library_history.run_scan
    assert isinstance(job.trigger, DateTrigger)


def test_the_start_scan_can_be_switched_off(monkeypatch):
    monkeypatch.setattr(settings, "library_scan_on_start", False)
    assert _job("library-scan-start") is None
