"""About me: the admin-only vocal/instrument trait choice list for tagging
a song request or broken report when reviewing it (app/routes/admin.py's
edit/admit routes) - not shown on the public request/report forms. A song
can carry several traits at once, stored as a comma-joined string on
SongRequest.trait / BrokenReport.trait (and their Pending* counterparts,
app/models.py), the same convention app/genres.py uses; parse_traits()/
format_traits() convert between that and a code list, trait_text() turns it
into display labels for the admin tables. The list is still
growing - only the choices themselves are expected to change.
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


def parse_traits(value: str | None) -> list[str]:
    if not value:
        return [DEFAULT_TRAIT]
    codes = [c for c in value.split(",") if c]
    return codes or [DEFAULT_TRAIT]


def format_traits(codes: list[str]) -> str:
    """Comma-joins the codes; "none" only stands alone, never next to a trait."""
    codes = [c for c in codes if c and c != DEFAULT_TRAIT]
    return ",".join(codes) if codes else DEFAULT_TRAIT


def trait_text(value: str | None) -> str:
    """The stored value as display labels, e.g. "Metal, Gothic" - the same
    codes the CSV export carries (an unknown code shows as itself)."""
    return ", ".join(TRAIT_LABELS.get(code, code) for code in parse_traits(value))
