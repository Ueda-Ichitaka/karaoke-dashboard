"""About me: the "production" vs "debug" app-wide mode (app/models.py:
AppSettings.mode), set via the admin Settings view. Production is this
app's normal, unchanged behavior. Debug raises the app's log level (see
app/app_logging.py) and lets an admin admit a pending song request for a
song that's already in the library (app/routes/admin.py's
pending_request_admit), for testing/troubleshooting without that guard.
"""

from __future__ import annotations

MODE_CHOICES: tuple[tuple[str, str], ...] = (
    ("production", "Production"),
    ("debug", "Debug"),
)

MODE_CODES: frozenset[str] = frozenset(code for code, _ in MODE_CHOICES)
