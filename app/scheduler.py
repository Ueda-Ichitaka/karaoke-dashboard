"""About me: schedules the background jobs, started and shut down from
app/main.py's lifespan:

- the automatic monthly rescan of the (expensive) duplicates report (see
  app/duplicates.py) - the admin view's "Rescan" button triggers the same
  refresh_cache() on demand;
- the library scan behind the songs page's "Recently added"/"Recently
  updated" lists (app/library_history.py), on a cron schedule and once at
  app start.

The schedules come from app/config.py, set via docker-compose.yml
environment variables so they can be adjusted without a rebuild.
The duplicates schedule comes from app/config.py (docker-compose.yml
environment variables). The library scan's schedule is a standard cron
expression (cron_trigger()) saved on the admin Settings page and passed in
at start; saving a new one reschedules the running job
(reschedule_library_scan). A stored expression that doesn't parse falls back
to DEFAULT_LIBRARY_SCAN_CRON rather than keeping the app from starting.
"""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from . import duplicates, library_history
from .app_logging import get_logger
from .config import settings
from .library_history import DEFAULT_LIBRARY_SCAN_CRON

logger = get_logger(__name__)

_CRON_WEEKDAYS = ("sun", "mon", "tue", "wed", "thu", "fri", "sat")


def _standard_weekdays(field: str) -> str:
    """Standard cron numbers weekdays from Sunday (0 and 7 are both Sunday),
    APScheduler 3 from Monday - so numeric parts become weekday names, which
    both read the same. "*" and names stay as they are."""
    parts: list[str] = []
    for part in field.split(","):
        base, _, step = part.partition("/")
        if base != "*" and not base.replace("-", "").isdigit():
            parts.append(part)
            continue
        if base == "*" and not step:
            parts.append(part)
            continue
        first, _, last = ("0", "", "6") if base == "*" else base.partition("-")
        days = range(int(first), int(last or (7 if step else first)) + 1, int(step or 1))
        if not days or days[0] > 7 or days[-1] > 7:
            raise ValueError(f"Invalid day of week: {part!r} (use 0-7 or sun-sat)")
        parts.extend(_CRON_WEEKDAYS[day % 7] for day in days)
    return ",".join(dict.fromkeys(parts))


def cron_trigger(expr: str) -> CronTrigger:
    """A trigger for a standard 5-field cron expression, weekdays included."""
    values = expr.split()
    if len(values) == 5:
        values[4] = _standard_weekdays(values[4])
    return CronTrigger.from_crontab(" ".join(values))


def create_scheduler(library_scan_cron: str = DEFAULT_LIBRARY_SCAN_CRON) -> AsyncIOScheduler:
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
    try:
        library_trigger = cron_trigger(library_scan_cron)
    except ValueError as err:
        logger.warning("library scan schedule %r is invalid (%s) - using %r", library_scan_cron, err,
                       DEFAULT_LIBRARY_SCAN_CRON)
        library_trigger = cron_trigger(DEFAULT_LIBRARY_SCAN_CRON)
    scheduler.add_job(library_history.run_scan, trigger=library_trigger, id="library-scan")
    if settings.library_scan_on_start:
        scheduler.add_job(library_history.run_scan, id="library-scan-start")  # no trigger: runs right away
    return scheduler


def reschedule_library_scan(scheduler: AsyncIOScheduler, library_scan_cron: str) -> None:
    """Moves the library scan to a new schedule (ValueError if it doesn't parse)."""
    scheduler.reschedule_job("library-scan", trigger=cron_trigger(library_scan_cron))
