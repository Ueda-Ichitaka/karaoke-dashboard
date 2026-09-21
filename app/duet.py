"""About me: the yes/no/blank "Duet" choice on the song-request form (and its
admin edit view) - whether a duet version of the requested song is wanted.
Blank means the requester didn't say; it's stored as NULL and exported as an
empty CSV cell.
"""

from __future__ import annotations

DUET_CHOICES: tuple[tuple[str, str], ...] = (
    ("", "Unspecified"),
    ("yes", "Yes"),
    ("no", "No"),
)

DUET_CODES: frozenset[str] = frozenset(code for code, _ in DUET_CHOICES if code)

DUET_LABELS: dict[str, str] = dict(DUET_CHOICES)


def is_valid_duet(value: str) -> bool:
    return value in DUET_CODES
