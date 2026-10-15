"""About me: the pieces the two admin CSV imports share - broken reports
(app/report_import.py) and song requests (app/request_import.py): reading
the uploaded file, the result shown on the import page, and the merge rules
for a row that lands on a song which already has a report or request. A
song never gets a second row; the row's information is merged in instead:

- a field the existing row lacks is filled in from the file;
- a lyrics link from lrclib.net wins over any other lyrics link, otherwise
  the existing link stays;
- genres/traits are combined (the "nothing special" default only stands
  alone);
- free text (a report's description) is appended unless already contained;
- any other field whose two values differ keeps the existing value, and the
  difference is listed on the import page as a note for the admin to check.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass
class SkippedRow:
    line: int
    reason: str


@dataclass
class ImportNote:
    line: int
    message: str


@dataclass
class ImportResult:
    imported: int = 0
    merged: int = 0
    skipped: list[SkippedRow] = field(default_factory=list)
    notes: list[ImportNote] = field(default_factory=list)


def decode_csv(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def read_rows(text: str, columns: tuple[str, ...], header_first_cells: set[str]) -> Iterator[tuple[int, dict]]:
    """(line number, {column: stripped value}) per non-blank row, matched to
    `columns` by position; a first row starting with one of
    `header_first_cells` is a header and skipped; missing trailing columns
    read as blank."""
    for line, row in enumerate(csv.reader(io.StringIO(text)), start=1):
        if not any(cell.strip() for cell in row):
            continue
        if line == 1 and row[0].strip().lower() in header_first_cells:
            continue
        cells = (list(row) + [""] * len(columns))[: len(columns)]
        yield line, {name: cell.strip() for name, cell in zip(columns, cells, strict=True)}


def parse_codes(raw: str, is_valid, label: str) -> tuple[list[str], str | None]:
    """A comma-joined genre/trait cell as codes, or the error for the first
    unrecognized one."""
    codes = [c.strip().lower() for c in raw.split(",") if c.strip()]
    for code in codes:
        if not is_valid(code):
            return [], f"Unrecognized {label}: {code}."
    return codes, None


def is_lrclib_url(url: str | None) -> bool:
    host = (urlsplit(url).hostname or "") if url else ""
    return host == "lrclib.net" or host.endswith(".lrclib.net")


def preferred_lyrics_link(existing: str | None, imported: str) -> str | None:
    if not imported:
        return existing
    if not existing or (is_lrclib_url(imported) and not is_lrclib_url(existing)):
        return imported
    return existing


def merge_codes(existing: str | None, imported: list[str], default: str) -> str:
    codes = [c for c in (existing or "").split(",") if c]
    codes += [c for c in imported if c not in codes]
    specific = [c for c in codes if c != default]
    return ",".join(specific) if specific else default


def append_new_text(existing: str | None, addition: str) -> str:
    existing = existing or ""
    if not addition or addition.lower() in existing.lower():
        return existing
    return f"{existing}; {addition}" if existing else addition


def keep_or_fill(existing: str | None, imported: str, label: str, notes: list[str]) -> str | None:
    """The existing value, filled in from `imported` when missing; a
    differing `imported` value adds a note to `notes`."""
    if not imported:
        return existing
    if not existing:
        return imported
    if existing != imported:
        notes.append(f'{label} differs: kept "{existing}", file has "{imported}"')
    return existing
