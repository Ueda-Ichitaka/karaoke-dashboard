"""About me: imports broken-song reports from a CSV in the existing broken.csv
export format (band, song name, category, description, lyrics_url, language,
cover_url, genre, trait - see app/routes/admin.py: reports_csv), for the
admin "Import CSV" upload on the Reported page. Used to bring in reports
prepared outside the app, e.g. by a library-repair script.

Each usable row becomes a PendingBrokenReport (Needs review), never an
admitted one - an admin still reviews, completes and admits it. A song never
gets a second report: a row for a song that already has an open or pending
report (app/report_matching.py: find_existing_report) - including an earlier
row of the same file - is merged into it by the shared import rules
(app/import_merge.py). A differing category is added to the description,
as for a second report from the public form. A song whose only report is
resolved is skipped. The song folder is resolved by an exact "band - song
name" folder match (case-insensitive), the same way the export derives
band/song name from the folder. Rows that can't be used (unknown folder,
unrecognized category/language/genre/trait, a link that isn't http(s)) are
skipped with a reason; the rest still import.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import songs as song_index
from .broken_categories import CATEGORY_LABELS, is_valid_category
from .genres import DEFAULT_GENRE, format_genres, is_valid_genre
from .import_merge import (
    ImportNote,
    ImportResult,
    SkippedRow,
    append_new_text,
    keep_or_fill,
    merge_codes,
    parse_codes,
    preferred_lyrics_link,
    read_rows,
)
from .languages import is_valid_language_code
from .models import BrokenReport, PendingBrokenReport, User
from .report_matching import find_existing_report
from .traits import DEFAULT_TRAIT, format_traits, is_valid_trait
from .validation import is_http_url, sanitize_free_text

COLUMNS = ("band", "song name", "category", "description", "lyrics_url", "language", "cover_url", "genre", "trait")
_HEADER_FIRST_CELLS = {"band", "band name"}


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


def _has_resolved_report(db: Session, folder: str) -> bool:
    stmt = select(BrokenReport.id).where(BrokenReport.song_folder == folder, BrokenReport.status == "resolved")
    return db.scalar(stmt.limit(1)) is not None


def _merge(
    existing: PendingBrokenReport | BrokenReport, values: dict[str, str], description: str,
    genres: list[str], traits: list[str],
) -> list[str]:
    """Merges one row into the song's existing report; returns the notes."""
    notes: list[str] = []
    pieces = []
    if values["category"] != existing.category:
        pieces.append(CATEGORY_LABELS.get(values["category"], values["category"]))
    if description:
        pieces.append(description)
    existing.description = append_new_text(existing.description, "; ".join(pieces))
    existing.genius_url = preferred_lyrics_link(existing.genius_url, values["lyrics_url"])
    existing.language = keep_or_fill(existing.language, values["language"], "language", notes)
    existing.cover_url = keep_or_fill(existing.cover_url, values["cover_url"], "cover link", notes)
    existing.genre = merge_codes(existing.genre, genres, DEFAULT_GENRE)
    existing.trait = merge_codes(existing.trait, traits, DEFAULT_TRAIT)
    return notes


def import_reports(db: Session, text: str, user: User) -> ImportResult:
    result = ImportResult()
    for line, values in read_rows(text, COLUMNS, _HEADER_FIRST_CELLS):
        for key in ("category", "language"):
            values[key] = values[key].lower()

        folder = song_index.folder_exists(values["band"], values["song name"])
        if folder is None:
            result.skipped.append(SkippedRow(line, f'No library folder "{values["band"]} - {values["song name"]}".'))
            continue
        error = _row_error(values)
        genres, genre_error = parse_codes(values["genre"], is_valid_genre, "genre")
        traits, trait_error = parse_codes(values["trait"], is_valid_trait, "trait")
        error = error or genre_error or trait_error
        if error:
            result.skipped.append(SkippedRow(line, error))
            continue

        description = sanitize_free_text(values["description"])
        existing = find_existing_report(db, folder)
        if existing is not None:
            notes = _merge(existing, values, description, genres, traits)
            result.notes.extend(ImportNote(line, f"{folder}: {note}") for note in notes)
            result.merged += 1
        elif _has_resolved_report(db, folder):
            result.skipped.append(SkippedRow(line, f'"{folder}" already has a resolved report.'))
            continue
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
