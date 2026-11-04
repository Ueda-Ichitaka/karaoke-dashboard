"""About me: the library scan behind the "Recently added" and "Recently
updated" lists on /songs (app/routes/songs.py). The library itself is only
folders and files without an "added" date, so a scheduled scan
(app/scheduler.py, on the schedule saved on the admin Settings page -
DEFAULT_LIBRARY_SCAN_CRON until one is saved - plus one run at app start)
records what it finds in LibraryFolder and the What's new page only reads
that.

- The very first scan (nothing recorded yet) counts every folder as old.
- After that, a new folder is a new song, dated by the scan that first sees
  it - listed once it follows the flat "Artist - Title" convention (the
  name has the separator and there's no nested subfolder, the same rule as
  app/structure_check.py).
- A write to a .txt, .mp3 or .opus file directly in a folder - a changed
  write time or size, or a new file - is an update (not to the USDX Song
  Factory's helper files, app/ultrastar.py: is_helper_file), dated by that file's
  write time. Writes within ADD_GRACE after a new folder was first seen are
  part of adding it (files still being copied in). Deleting a file is not
  an update.

Every scan, the very first included, also records each folder's newest
song-file write time (last_write_at; it only ever moves forward).
last_writes() - the newer of that and the last detected change - is what
the "is it fixed" checks compare a report's time with: the admin Reported
page's mark on both its tables (updated_since_report) and the public badge's "until updated"
mode (app/known_broken.py). So a fix written before the first scan counts
too.

Every scan also stores each folder's genres, read from its song files, for
the Genres page (record_genres, app/song_genres.py).

The admin Settings page runs the scan on demand (run_scan) and can reset
the history (run_reset): forget everything recorded and scan again as a
very first scan.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .app_logging import get_logger
from .config import settings
from .database import SessionLocal
from .models import BrokenReport, LibraryFolder, PendingBrokenReport
from .song_genres import record_genres
from .songs import Song, parse_folder
from .ultrastar import is_helper_file

SONG_FILE_EXTENSIONS = (".txt", ".mp3", ".opus")
DEFAULT_LIBRARY_SCAN_CRON = "0 11 * * *"  # daily at 11:00
ADD_GRACE = timedelta(hours=1)

logger = get_logger(__name__)
_scan_lock = threading.Lock()


def as_utc(moment: datetime) -> datetime:
    """A stored datetime as an aware UTC one - SQLite hands back naive
    datetimes, and every stored one is UTC."""
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _folder_names(root: Path) -> list[str]:
    ignore = set(settings.song_ignore_names)
    try:
        with os.scandir(root) as entries:
            return [e.name for e in entries if not e.name.startswith(".") and e.name not in ignore and e.is_dir()]
    except OSError:
        return []


def _read_folder(path: Path) -> tuple[bool, dict[str, list[float]]]:
    """Whether the folder has a nested subfolder, and its song files as
    {filename: [mtime, size]}."""
    ignore = set(settings.song_ignore_names)
    nested = False
    files: dict[str, list[float]] = {}
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                try:
                    if entry.is_dir():
                        nested = nested or entry.name not in ignore
                    elif (entry.is_file() and os.path.splitext(entry.name)[1].lower() in SONG_FILE_EXTENSIONS
                          and not is_helper_file(entry.name)):
                        stat = entry.stat()
                        files[entry.name] = [stat.st_mtime, stat.st_size]
                except OSError:
                    continue
    except OSError:
        pass
    return nested, files


def _newest_write(before: dict[str, list[float]], now: dict[str, list[float]],
                  first_seen_at: datetime | None) -> datetime | None:
    """Write time of the newest file that is new or changed since "before",
    leaving out writes within ADD_GRACE after a new folder was first seen."""
    grace_end = as_utc(first_seen_at) + ADD_GRACE if first_seen_at else None
    writes = [
        datetime.fromtimestamp(mtime_size[0], UTC)
        for name, mtime_size in now.items()
        if before.get(name) != mtime_size
    ]
    writes = [w for w in writes if grace_end is None or w > grace_end]
    return max(writes, default=None)


def scan_library(db: Session, *, root: str | Path | None = None, now: datetime | None = None) -> bool:
    """Records new folders and song-file writes since the last scan. False
    when the library can't be read (nothing recorded)."""
    root = Path(root if root is not None else settings.songs_dir)
    now = now or datetime.now(UTC)
    names = _folder_names(root)
    if not names:
        return False  # an unreadable or unmounted library must not count as the first scan
    rows = {row.folder: row for row in db.scalars(select(LibraryFolder))}
    first_scan = not rows
    for name in names:
        nested, files = _read_folder(root / name)
        follows_convention = parse_folder(name).artist is not None and not nested
        newest = max((datetime.fromtimestamp(mtime, UTC) for mtime, _ in files.values()), default=None)
        row = rows.get(name)
        if row is None:
            db.add(LibraryFolder(folder=name, first_seen_at=None if first_scan else now,
                                 follows_convention=follows_convention, files=json.dumps(files),
                                 last_write_at=newest))
            continue
        if newest and (row.last_write_at is None or newest > as_utc(row.last_write_at)):
            row.last_write_at = newest
        if row.files is not None:
            written = _newest_write(json.loads(row.files), files, row.first_seen_at)
            if written and (row.updated_at is None or written > as_utc(row.updated_at)):
                row.updated_at = written
        row.follows_convention = follows_convention
        row.files = json.dumps(files)
    record_genres(db, root, names)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # another scan recorded the same new folders first
    return True


def reset_library(db: Session, *, root: str | Path | None = None, now: datetime | None = None) -> None:
    """Forgets everything recorded and scans again as a very first scan, so
    every current folder counts as old. Keeps the history when the library
    can't be read."""
    db.execute(delete(LibraryFolder))
    if not scan_library(db, root=root, now=now):
        db.rollback()


def run_scan() -> None:
    """The scheduled job and the Settings page's "Scan now": one scan of the
    real library, never two at once."""
    with _scan_lock, SessionLocal() as db:
        scan_library(db)
    logger.info("library scan done")


def run_reset() -> None:
    """The Settings page's "Reset": reset_library() on the real library."""
    with _scan_lock, SessionLocal() as db:
        reset_library(db)
    logger.info("library history reset")


def _recent(db: Session, songs: list[Song], column, since: datetime, *conditions) -> list[tuple[Song, datetime]]:
    by_folder = {song.folder: song for song in songs}
    rows = db.execute(
        select(LibraryFolder.folder, column)
        .where(column >= since, *conditions)
        .order_by(column.desc(), LibraryFolder.folder)
    )
    return [(by_folder[folder], moment) for folder, moment in rows if folder in by_folder]


def recent_additions(db: Session, songs: list[Song], since: datetime) -> list[tuple[Song, datetime]]:
    """The library songs first seen at or after "since" that follow the
    folder convention, newest first."""
    return _recent(db, songs, LibraryFolder.first_seen_at, since, LibraryFolder.follows_convention.is_(True))


def recent_updates(db: Session, songs: list[Song], since: datetime) -> list[tuple[Song, datetime]]:
    """The library songs with a song-file write at or after "since", newest first."""
    return _recent(db, songs, LibraryFolder.updated_at, since)


def last_writes(db: Session, folders: set[str]) -> dict[str, datetime]:
    """Each of these folders' last known song-file write - the newer of the
    newest write time a scan read and the last detected change - where
    there is one."""
    if not folders:
        return {}
    rows = db.execute(
        select(LibraryFolder.folder, LibraryFolder.last_write_at, LibraryFolder.updated_at)
        .where(LibraryFolder.folder.in_(folders))
    )
    writes = {folder: [as_utc(t) for t in (last_write, updated) if t] for folder, last_write, updated in rows}
    return {folder: max(times) for folder, times in writes.items() if times}


def updated_since_report(db: Session, reports: list[BrokenReport] | list[PendingBrokenReport]) -> dict[int, datetime]:
    """Maps the id of each report - all admitted or all awaiting review, the
    two tables' ids overlap - whose song had a recorded update after the
    report was drafted to that update's time."""
    updates = last_writes(db, {report.song_folder for report in reports})
    return {
        report.id: updates[report.song_folder]
        for report in reports
        if report.song_folder in updates and updates[report.song_folder] > as_utc(report.created_at)
    }
