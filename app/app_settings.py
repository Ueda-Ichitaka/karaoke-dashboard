"""About me: fetches the admin-editable AppSettings singleton row (see
app/models.py), creating it with defaults on first use. Used by the public
request/report routes to pick which profile (app/profiles.py) currently
applies, by the public song pages for the "Reported broken" badge mode
(app/broken_badge.py) and the "What's new" period (app/recent_period.py),
at app start for the library scan schedule (app/main.py), and by the admin
Settings view (app/routes/admin.py) to
show/update it.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from .broken_badge import UNTIL_RESOLVED
from .library_history import DEFAULT_LIBRARY_SCAN_CRON
from .models import AppSettings
from .recent_period import DEFAULT_AMOUNT, DEFAULT_UNIT

_SINGLETON_ID = 1


def get_app_settings(db: Session) -> AppSettings:
    settings = db.get(AppSettings, _SINGLETON_ID)
    if settings is None:
        settings = AppSettings(id=_SINGLETON_ID)
        db.add(settings)
        db.commit()
    if settings.mode is None:
        # Backfills a row created before AppSettings.mode existed (nullable
        # only so _sync_schema could auto-add it to the existing table).
        settings.mode = "production"
        db.commit()
    if settings.logging_enabled is None:
        settings.logging_enabled = True
        db.commit()
    if settings.broken_badge is None:
        settings.broken_badge = UNTIL_RESOLVED
        db.commit()
    if settings.library_scan_cron is None:
        settings.library_scan_cron = DEFAULT_LIBRARY_SCAN_CRON
        db.commit()
    if settings.recent_amount is None or settings.recent_unit is None:
        settings.recent_amount, settings.recent_unit = DEFAULT_AMOUNT, DEFAULT_UNIT
        db.commit()
    return settings
