"""About me: schedules the automatic monthly rescan of the (expensive)
duplicates report (see app/duplicates.py) - the admin view's "Rescan" button
triggers the same refresh_cache() on demand. The schedule itself
(day-of-month + time) comes from app/config.py, set via docker-compose.yml
environment variables so it can be adjusted without a rebuild. Started and
shut down from app/main.py's lifespan.
"""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from . import duplicates
from .config import settings


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        duplicates.refresh_cache,
        trigger=CronTrigger(
            day=settings.duplicates_rescan_day,
            hour=settings.duplicates_rescan_hour,
            minute=settings.duplicates_rescan_minute,
        ),
        id="duplicates-rescan",
    )
    return scheduler
