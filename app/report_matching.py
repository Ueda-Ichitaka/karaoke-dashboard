"""About me: duplicate handling for broken-song reports (app/routes/reports.py).
Rather than blocking a second report for a song that already has an open one,
find_existing_report locates it and merge_into_existing_report folds the new
submission's data into it - the same known issue stays a single row instead
of piling up duplicates.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .broken_categories import CATEGORY_LABELS
from .models import BrokenReport


def find_existing_report(db: Session, song_folder: str) -> BrokenReport | None:
    """The oldest still-open report for this exact song folder, if any.

    A resolved report no longer matches - a fresh report against the same
    song is treated as a new occurrence, not a duplicate of a fixed issue.
    """
    song_folder = song_folder.strip()
    if not song_folder:
        return None
    return db.scalar(
        select(BrokenReport)
        .where(BrokenReport.song_folder == song_folder, BrokenReport.status == "open")
        .order_by(BrokenReport.created_at.asc())
    )


def merge_into_existing_report(
    existing: BrokenReport, *, category: str, description: str, genius_url: str, cover_url: str
) -> None:
    """Folds a new duplicate report's data into an already-open one.

    The lyrics/cover links only fill in if the existing report doesn't have
    one yet. The description always accumulates instead: a category that
    differs from the existing report's is noted (the category field itself
    isn't changed - the original report stays the canonical one), and any
    new description text is appended after it.
    """
    pieces = []
    if category != existing.category:
        pieces.append(CATEGORY_LABELS.get(category, category))
    if description:
        pieces.append(description)
    if pieces:
        addition = "; ".join(pieces)
        existing.description = f"{existing.description}; {addition}" if existing.description else addition

    if not existing.genius_url and genius_url:
        existing.genius_url = genius_url
    if not existing.cover_url and cover_url:
        existing.cover_url = cover_url
