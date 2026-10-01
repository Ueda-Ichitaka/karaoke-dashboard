"""About me: the yes/no "Duet" choice on the song-request form (and its admin
edit view) - whether a duet version of the requested song is wanted. The form
only offers Yes/No (no blank option) and defaults to "No". Blank/NULL only
remains reachable on rows stored before this field existed or before the
blank option was removed; wants_duet() treats it the same as an explicit
"No", both on this side (app/request_matching.py's duplicate check) and, per
UPSTREAM_REQUESTS.md, on the UltraSinger side.
"""

from __future__ import annotations

DUET_CHOICES: tuple[tuple[str, str], ...] = (
    ("yes", "Yes"),
    ("no", "No"),
)

DUET_CODES: frozenset[str] = frozenset(code for code, _ in DUET_CHOICES if code)

DUET_LABELS: dict[str, str] = dict(DUET_CHOICES)


def is_valid_duet(value: str) -> bool:
    return value in DUET_CODES


def wants_duet(value: str | None) -> bool:
    """True only for an explicit "yes" - blank/"no"/anything else means no."""
    return value == "yes"
