"""Tests for app/scheduler.py: the automatic monthly rescan of the
(expensive) duplicates report - see app/duplicates.py and its "Rescan"
button for the on-demand equivalent.
"""

from __future__ import annotations

from app import duplicates
from app.config import settings
from app.scheduler import create_scheduler


def test_scheduler_has_one_job_matching_the_configured_schedule():
    scheduler = create_scheduler()
    jobs = scheduler.get_jobs()
    assert len(jobs) == 1
    fields = {f.name: str(f) for f in jobs[0].trigger.fields}
    assert fields["day"] == str(settings.duplicates_rescan_day)
    assert fields["hour"] == str(settings.duplicates_rescan_hour)
    assert fields["minute"] == str(settings.duplicates_rescan_minute)


def test_scheduler_job_refreshes_the_duplicates_cache():
    scheduler = create_scheduler()
    job = scheduler.get_jobs()[0]
    assert job.func is duplicates.refresh_cache
