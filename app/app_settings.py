"""About me: fetches the admin-editable AppSettings singleton row (see
app/models.py), creating it with defaults on first use. Used by the public
request/report routes to pick which profile (app/profiles.py) currently
applies, and by the admin Settings view (app/routes/admin.py) to show/update
it.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from .models import AppSettings

_SINGLETON_ID = 1


def get_app_settings(db: Session) -> AppSettings:
    settings = db.get(AppSettings, _SINGLETON_ID)
    if settings is None:
        settings = AppSettings(id=_SINGLETON_ID)
        db.add(settings)
        db.commit()
    return settings
