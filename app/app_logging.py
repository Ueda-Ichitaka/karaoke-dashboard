"""About me: the app's logging knobs - a level raised to DEBUG while the
admin Settings view's mode is "debug" (app/app_mode.py), INFO in
"production", and a separate "enable logging" toggle that can silence
everything regardless of mode. configure_logging() is called once at
startup (app/main.py, with the persisted AppSettings.mode/logging_enabled)
and again whenever an admin changes either one (app/routes/admin.py:
settings_update), so the change takes effect immediately without a
restart. get_logger() is a thin wrapper so call sites don't need to import
the stdlib logging module directly.
"""

from __future__ import annotations

import logging

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_configured = False


def configure_logging(mode: str, enabled: bool = True) -> None:
    global _configured
    level = logging.DEBUG if mode == "debug" else logging.INFO
    if not _configured:
        logging.basicConfig(level=level, format=_FORMAT)
        _configured = True
    logging.getLogger().setLevel(level)
    # disable(CRITICAL) suppresses every record at CRITICAL and below, i.e.
    # everything; NOTSET lifts that back off instead of changing any level.
    logging.disable(logging.CRITICAL if not enabled else logging.NOTSET)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
