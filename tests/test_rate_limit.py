"""Tests for app/rate_limit.py: a small in-memory brute-force guard,
tracking failed attempts per key (the caller decides what a "key" is - for
login, the client IP - see app/routes/auth.py) within a sliding window.
"""

from __future__ import annotations

from app import rate_limit


def test_not_locked_out_before_any_failures():
    rate_limit.reset()
    assert rate_limit.is_locked_out("1.2.3.4") is False


def test_locked_out_after_max_attempts():
    rate_limit.reset()
    for _ in range(rate_limit.MAX_ATTEMPTS):
        rate_limit.record_failure("1.2.3.4")
    assert rate_limit.is_locked_out("1.2.3.4") is True


def test_not_locked_out_one_below_max_attempts():
    rate_limit.reset()
    for _ in range(rate_limit.MAX_ATTEMPTS - 1):
        rate_limit.record_failure("1.2.3.4")
    assert rate_limit.is_locked_out("1.2.3.4") is False


def test_success_clears_recorded_failures():
    rate_limit.reset()
    for _ in range(rate_limit.MAX_ATTEMPTS):
        rate_limit.record_failure("1.2.3.4")
    rate_limit.record_success("1.2.3.4")
    assert rate_limit.is_locked_out("1.2.3.4") is False


def test_keys_are_independent():
    rate_limit.reset()
    for _ in range(rate_limit.MAX_ATTEMPTS):
        rate_limit.record_failure("1.2.3.4")
    assert rate_limit.is_locked_out("5.6.7.8") is False


def test_old_failures_outside_the_window_do_not_count(monkeypatch):
    rate_limit.reset()
    clock = [1000.0]
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: clock[0])

    for _ in range(rate_limit.MAX_ATTEMPTS):
        rate_limit.record_failure("1.2.3.4")
    assert rate_limit.is_locked_out("1.2.3.4") is True

    clock[0] += rate_limit.WINDOW_SECONDS + 1
    assert rate_limit.is_locked_out("1.2.3.4") is False
