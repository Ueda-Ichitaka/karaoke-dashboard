"""About me: imports broken-song reports from a CSV in the existing broken.csv
export format (band, song name, category, description, lyrics_url, language,
cover_url, genre, trait - see app/routes/admin.py: reports_csv), for the
admin "Import CSV" upload on the Reported page. Used to bring in reports
prepared outside the app, e.g. by a library-repair script.

Each usable row becomes a PendingBrokenReport (Needs review), never an
admitted one - an admin still reviews, completes and admits it. A row for a
song that already has an open or pending report merges into it instead,
exactly like a second report from the public form (app/report_matching.py),
including a second row for the same song within one file. The song folder
is resolved by an exact "band - song name" folder match (case-insensitive),
the same way the export derives band/song name from the folder. Rows that
can't be used (unknown folder, unrecognized category/language/genre/trait,
a link that isn't http(s)) are skipped with a reason; the rest still import.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from . import songs as song_index
from .broken_categories import is_valid_category
from .genres import format_genres, is_valid_genre
from .languages import is_valid_language_code
from .models import PendingBrokenReport, User
from .report_matching import find_existing_report, merge_into_existing_report
from .traits import format_traits, is_valid_trait
from .validation import is_http_url, sanitize_free_text

COLUMNS = ("band", "song name", "category", "description", "lyrics_url", "language", "cover_url", "genre", "trait")
_HEADER_FIRST_CELLS = {"band", "band name"}


@dataclass
class SkippedRow:
    line: int
    reason: str


@dataclass
class ImportResult:
    imported: int = 0
    merged: int = 0
    skipped: list[SkippedRow] = field(default_factory=list)


def decode_csv(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _codes(raw: str, is_valid, label: str) -> tuple[list[str], str | None]:
    codes = [c.strip().lower() for c in raw.split(",") if c.strip()]
    for code in codes:
        if not is_valid(code):
            return [], f"Unrecognized {label}: {code}."
    return codes, None


def _row_error(values: dict[str, str]) -> str | None:
    if not is_valid_category(values["category"]):
        return f"Unrecognized category: {values['category'] or '(blank)'}."
    if values["language"] and not is_valid_language_code(values["language"]):
        return f"Unrecognized language: {values['language']}."
    if values["lyrics_url"] and not is_http_url(values["lyrics_url"]):
        return "The lyrics link must start with http:// or https://"
    if values["cover_url"] and not is_http_url(values["cover_url"]):
        return "The cover image link must start with http:// or https://"
    return None


def import_reports(db: Session, text: str, user: User) -> ImportResult:
    result = ImportResult()
    for line, row in enumerate(csv.reader(io.StringIO(text)), start=1):
        if not any(cell.strip() for cell in row):
            continue
        if line == 1 and row[0].strip().lower() in _HEADER_FIRST_CELLS:
            continue
        values = dict(zip(COLUMNS, (list(row) + [""] * len(COLUMNS))[: len(COLUMNS)], strict=True))
        values = {k: v.strip() for k, v in values.items()}
        for key in ("category", "language"):
            values[key] = values[key].lower()

        folder = song_index.folder_exists(values["band"], values["song name"])
        if folder is None:
            result.skipped.append(SkippedRow(line, f'No library folder "{values["band"]} - {values["song name"]}".'))
            continue
        error = _row_error(values)
        genres, genre_error = _codes(values["genre"], is_valid_genre, "genre")
        traits, trait_error = _codes(values["trait"], is_valid_trait, "trait")
        error = error or genre_error or trait_error
        if error:
            result.skipped.append(SkippedRow(line, error))
            continue

        description = sanitize_free_text(values["description"])
        existing = find_existing_report(db, folder)
        if existing is not None:
            merge_into_existing_report(
                existing, category=values["category"], description=description,
                genius_url=values["lyrics_url"], cover_url=values["cover_url"],
            )
            result.merged += 1
        else:
            db.add(
                PendingBrokenReport(
                    song_folder=folder,
                    category=values["category"],
                    description=description,
                    genius_url=values["lyrics_url"] or None,
                    language=values["language"] or None,
                    cover_url=values["cover_url"] or None,
                    genre=format_genres(genres),
                    trait=format_traits(traits),
                    reporter_id=user.id,
                    reporter_username=user.username,
                )
            )
            result.imported += 1
        db.flush()  # a later row for the same song must find this one
    db.commit()
    return result
