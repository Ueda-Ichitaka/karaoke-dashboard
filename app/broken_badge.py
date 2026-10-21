"""About me: the modes of the "Reported broken" badge on the public song
list and the "What's new" page (app/models.py: AppSettings.broken_badge),
set via the admin Settings view. "until_resolved" keeps the badge until an
admin resolves the report; "until_updated" also drops it once the song's
files were written after the report was drafted (app/known_broken.py). The
admin report lists don't depend on it.
"""

from __future__ import annotations

UNTIL_RESOLVED = "until_resolved"
UNTIL_UPDATED = "until_updated"

BADGE_MODE_CHOICES: tuple[tuple[str, str], ...] = (
    (UNTIL_RESOLVED, "Until the report is resolved"),
    (UNTIL_UPDATED, "Until the song is updated or the report resolved"),
)

BADGE_MODE_CODES: frozenset[str] = frozenset(code for code, _ in BADGE_MODE_CHOICES)
