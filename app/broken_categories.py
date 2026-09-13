"""About me: the fixed category list for the "report a broken song" form -
mandatory on every report so downstream processing can act on the kind of
breakage without parsing free text. "other" is the only category that also
requires the free-text description; every other category is specific enough
to be useful on its own.
"""

from __future__ import annotations

CATEGORY_CHOICES: tuple[tuple[str, str], ...] = (
    ("gap", "#GAP (song starts too early/late)"),
    ("async", "Song goes out of sync"),
    ("lyrics", "Lyrics broken"),
    ("video", "Missing video"),
    ("audio", "Missing audio"),
    ("other", "Other"),
)

CATEGORY_CODES: frozenset[str] = frozenset(code for code, _ in CATEGORY_CHOICES)

CATEGORY_LABELS: dict[str, str] = dict(CATEGORY_CHOICES)


def is_valid_category(code: str) -> bool:
    return code in CATEGORY_CODES
