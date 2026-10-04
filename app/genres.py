"""About me: the admin-only genre choice list for tagging a song request or
broken report when reviewing it (app/routes/admin.py's edit/admit routes) -
not shown on the public request/report forms. A song can carry several
genres at once, stored as a comma-joined string on SongRequest.genre /
BrokenReport.genre (and their Pending* counterparts, app/models.py); parse_
genres()/format_genres() convert between that and a code list. The list is
still growing - only the choices themselves are expected to change.
"""

from __future__ import annotations

GENRE_CHOICES: tuple[tuple[str, str], ...] = (
    ("default", "Default"),
    ("metal", "Metal"),
    ("medieval", "Medieval"),
    ("folk", "Folk"),
    ("gothic", "Gothic"),
    ("symphonic", "Symphonic"),
    ("punk", "Punk"),
    ("pop", "Pop"),
    ("rap", "Rap"),
    ("kpop", "K-pop"),
    ("jpop", "J-pop"),
)

GENRE_CODES: frozenset[str] = frozenset(code for code, _ in GENRE_CHOICES)
GENRE_LABELS: dict[str, str] = dict(GENRE_CHOICES)
DEFAULT_GENRE = "default"


def is_valid_genre(code: str) -> bool:
    return code in GENRE_CODES


def parse_genres(value: str | None) -> list[str]:
    if not value:
        return [DEFAULT_GENRE]
    codes = [c for c in value.split(",") if c]
    return codes or [DEFAULT_GENRE]


def format_genres(codes: list[str]) -> str:
    codes = [c for c in codes if c]
    return ",".join(codes) if codes else DEFAULT_GENRE
