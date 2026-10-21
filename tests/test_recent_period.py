"""Tests for app/recent_period.py: the "What's new" period - a whole number
of days, weeks or (calendar) months - turned into the exact moment the two
lists start from, keeping the time of day.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.recent_period import (
    DEFAULT_AMOUNT,
    DEFAULT_UNIT,
    MAX_AMOUNT,
    UNIT_CHOICES,
    describe,
    is_valid_unit,
    months_before,
    period_start,
)

NOW = datetime(2026, 10, 18, 11, 30, tzinfo=UTC)


def test_the_default_is_two_months():
    assert (DEFAULT_AMOUNT, DEFAULT_UNIT) == (2, "months")


def test_days_weeks_and_months_are_offered():
    assert [code for code, _ in UNIT_CHOICES] == ["days", "weeks", "months"]
    assert all(is_valid_unit(code) for code, _ in UNIT_CHOICES)
    assert not is_valid_unit("hours")
    assert MAX_AMOUNT == 999


def test_days_and_weeks_go_back_exactly_keeping_the_time():
    assert period_start(NOW, 3, "days") == NOW - timedelta(days=3)
    assert period_start(NOW, 2, "weeks") == datetime(2026, 10, 4, 11, 30, tzinfo=UTC)


def test_months_go_back_calendar_months_keeping_the_time():
    assert period_start(NOW, 2, "months") == datetime(2026, 8, 18, 11, 30, tzinfo=UTC)


def test_months_before_counts_calendar_months():
    assert months_before(NOW, 2) == datetime(2026, 8, 18, 11, 30, tzinfo=UTC)
    assert months_before(datetime(2026, 1, 15, tzinfo=UTC), 2) == datetime(2025, 11, 15, tzinfo=UTC)
    assert months_before(datetime(2026, 4, 30, tzinfo=UTC), 2) == datetime(2026, 2, 28, tzinfo=UTC)
    assert months_before(NOW, 999) == datetime(1943, 7, 18, 11, 30, tzinfo=UTC)


def test_describe_reads_naturally():
    assert describe(2, "months") == "2 months"
    assert describe(1, "weeks") == "1 week"
    assert describe(1, "days") == "1 day"
    assert describe(10, "days") == "10 days"
