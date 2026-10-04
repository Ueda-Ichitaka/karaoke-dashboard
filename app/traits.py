"""About me: the admin-only vocal/instrument trait choice list for tagging
a song request or broken report when reviewing it (app/routes/admin.py's
edit/admit routes) - not shown on the public request/report forms. Unlike
app/genres.py, only one trait applies at a time, stored directly on
SongRequest.trait / BrokenReport.trait (and their Pending* counterparts,
app/models.py). The list is still growing - only the choices themselves are
expected to change.
"""

from __future__ import annotations

TRAIT_CHOICES: tuple[tuple[str, str], ...] = (
    ("none", "None"),
    ("harsh_vocals", "Harsh vocals"),
    ("operatic_vocals", "Operatic vocals"),
    ("loud_high_instruments", "Loud high instruments"),
    ("choir", "Choir"),
)

TRAIT_CODES: frozenset[str] = frozenset(code for code, _ in TRAIT_CHOICES)
TRAIT_LABELS: dict[str, str] = dict(TRAIT_CHOICES)
DEFAULT_TRAIT = "none"


def is_valid_trait(code: str) -> bool:
    return code in TRAIT_CODES
