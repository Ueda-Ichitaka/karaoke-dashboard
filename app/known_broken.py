"""About me: which library song folders are currently known to be broken,
for the "Reported broken" badge on the public song list and the "What's
new" page (app/routes/songs.py). A song counts while it has a report
awaiting review (PendingBrokenReport) or an admitted report still open
(BrokenReport); a resolved report doesn't. In the "until updated" badge
mode (app/broken_badge.py), neither does a report the song's files were
written after (the library scan's LibraryFolder.updated_at,
app/library_history.py) - the admin report lists are never affected.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .broken_categories import CATEGORY_LABELS
from .library_history import as_utc, folder_updates
from .models import BrokenReport, PendingBrokenReport


def known_broken(db: Session, until_updated: bool = False) -> dict[str, str]:
    """Maps each broken song folder to its reports' category labels -
    distinct, comma-joined, pending reports first ("" when no report names
    a category). With until_updated, a report the song was updated after
    doesn't count."""
    rows = [
        *db.execute(select(PendingBrokenReport.song_folder, PendingBrokenReport.category,
                           PendingBrokenReport.created_at).order_by(PendingBrokenReport.id)),
        *db.execute(select(BrokenReport.song_folder, BrokenReport.category, BrokenReport.created_at)
                    .where(BrokenReport.status == "open").order_by(BrokenReport.id)),
    ]
    updates = folder_updates(db, {folder for folder, _, _ in rows}) if until_updated else {}
    labels: dict[str, list[str]] = {}
    for folder, category, created_at in rows:
        if folder in updates and updates[folder] > as_utc(created_at):
            continue
        folder_labels = labels.setdefault(folder, [])
        label = CATEGORY_LABELS.get(category, category) if category else ""
        if label and label not in folder_labels:
            folder_labels.append(label)
    return {folder: ", ".join(folder_labels) for folder, folder_labels in labels.items()}
