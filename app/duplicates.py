"""About me: detects duplicate songs across the library for admin review.

Two UltraStar entries (each parsed from a .txt file, possibly in different
folders) are the same song if their artist and title match after
normalization and they agree on duet status - a duet arrangement and a solo
arrangement of the same song are an intentional variant, not a duplicate.
Groups of two or more matching entries are duplicates.

A second, looser comparison (loose_key: ignores "(...)"/"[...]" asides and
treats filename-unsafe characters and the dash that replaces them alike)
finds *versions* of a song - "Skyfall" vs "Skyfall (Full Length)", a live
or album version - listed apart as possible duplicates, since many are kept
on purpose. Only loose groups whose entries differ in their exact title
count; their keys carry VERSION_KEY_PREFIX, so dismissing a version group
and dismissing an exact group never affect each other. The same scan also
lists song folders without any UltraStar song file (empty, or media only),
except the set-aside folder "-" (app/songs.py: SET_ASIDE_FOLDER).

Scanning every folder's UltraStar tags to build these groups is expensive,
so the result is cached in memory (see _cache below) rather than recomputed
on every page view - refresh_cache() replaces it, called by an admin's
"Rescan" button (see app/routes/admin.py) and by the scheduled monthly job
(see app/scheduler.py). An admin "dismisses" a group by recording its
normalized key in the dismissed_duplicates table (see app/models.py), which
future lookups then skip - dismissal is looked up fresh from the database on
every call, independent of the group cache.
"""

from __future__ import annotations

import hashlib
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import songs, ultrastar
from .config import settings
from .models import DismissedDuplicate

_WHITESPACE = re.compile(r"\s+")
_BRACKETED_RE = re.compile(r"\([^)]*\)|\[[^\]]*\]")
_NOISE_SUBSTRINGS = ("napalm records",)
_FILENAME_UNSAFE_RE = re.compile(r'[\\/:*?"<>|-]')

VERSION_KEY_PREFIX = "version:"

# (label, SongMeta attribute) pairs compared in the detail-view diff table.
_DIFF_FIELDS: tuple[tuple[str, str], ...] = (
    ("Artist", "artist"),
    ("Title", "title"),
    ("Genre", "genre"),
    ("Year", "year"),
    ("Language", "language"),
    ("Length", "length_display"),
    ("Duet", "is_duet"),
    ("Cover file", "cover_file"),
)


def normalize_key(text: str | None) -> str:
    """Fold a title/artist to a comparable key: casefold, trim, collapse spaces."""
    if not text:
        return ""
    return _WHITESPACE.sub(" ", text.strip().casefold())


def loose_key(text: str | None) -> str:
    """A looser comparison key than normalize_key: also ignores parenthesized/
    bracketed asides and a couple of known noise suffixes (e.g. a record
    label pulled in from a source video's title), treats filename-unsafe
    characters and the "-" that commonly replaces them alike (a real ":" or
    "/" in a tag is often dropped or swapped for a dash in a folder/file
    name), and ignores a trailing "." or space, which Windows/exFAT strips
    from a folder name. Shared with app/misplaced_check.py.
    """
    cleaned = _BRACKETED_RE.sub(" ", text or "")
    lowered = cleaned.casefold()
    for noise in _NOISE_SUBSTRINGS:
        lowered = lowered.replace(noise, " ")
    lowered = _FILENAME_UNSAFE_RE.sub(" ", lowered)
    return normalize_key(lowered).rstrip(". ")


def _group_id(artist_key: str, title_key: str, is_duet: bool) -> str:
    raw = f"{artist_key}\x1f{title_key}\x1f{is_duet}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class DuplicateEntry:
    folder: str
    meta: ultrastar.SongMeta


@dataclass(frozen=True, slots=True)
class DuplicateGroup:
    group_id: str
    artist_key: str
    title_key: str
    is_duet: bool
    entries: list[DuplicateEntry]
    is_version: bool = False

    @property
    def display_title(self) -> str:
        return self.entries[0].meta.title

    @property
    def display_artist(self) -> str | None:
        return self.entries[0].meta.artist


@dataclass(frozen=True, slots=True)
class FieldRow:
    label: str
    values: list[str]
    differs: bool


def _display(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def field_diff(group: DuplicateGroup) -> list[FieldRow]:
    rows = []
    for label, attr in _DIFF_FIELDS:
        values = [_display(getattr(e.meta, attr)) for e in group.entries]
        rows.append(FieldRow(label=label, values=values, differs=len(set(values)) > 1))
    return rows


@dataclass(frozen=True, slots=True)
class EmptyFolder:
    folder: str
    file_count: int


@dataclass
class _Scan:
    groups: list[DuplicateGroup] = field(default_factory=list)
    version_groups: list[DuplicateGroup] = field(default_factory=list)
    empty_folders: list[EmptyFolder] = field(default_factory=list)


def _build_groups(buckets: dict[tuple[str, str, bool], list[DuplicateEntry]], is_version: bool) -> list[DuplicateGroup]:
    groups = [
        DuplicateGroup(
            group_id=_group_id(*key),
            artist_key=key[0],
            title_key=key[1],
            is_duet=key[2],
            entries=sorted(entries, key=lambda e: (e.folder, e.meta.source_file)),
            is_version=is_version,
        )
        for key, entries in buckets.items()
        if len(entries) > 1
        and (not is_version or len({normalize_key(e.meta.title) for e in entries}) > 1)
    ]
    groups.sort(key=lambda g: ((g.display_artist or "").lower(), g.display_title.lower()))
    return groups


def _empty_folder(folder: str) -> EmptyFolder | None:
    """A folder with no song file - unless it has subfolders, which is the
    integrity view's structure check's concern instead."""
    try:
        entries = list(os.scandir(Path(settings.songs_dir) / folder))
    except OSError:
        return None
    if any(e.is_dir() for e in entries):
        return None
    return EmptyFolder(folder=folder, file_count=len(entries))


def _scan_library() -> _Scan:
    """Every duplicate group, version group and song-less folder in the
    library right now, dismissed or not.

    The expensive part: scans every folder's UltraStar tags from disk.
    """
    exact: dict[tuple[str, str, bool], list[DuplicateEntry]] = {}
    loose: dict[tuple[str, str, bool], list[DuplicateEntry]] = {}
    empty: list[EmptyFolder] = []
    for song in songs.all_songs():
        metas = ultrastar.scan_folder_songs(song.folder)
        if not metas and song.folder != songs.SET_ASIDE_FOLDER:
            folder = _empty_folder(song.folder)
            if folder is not None:
                empty.append(folder)
        for meta in metas:
            entry = DuplicateEntry(folder=song.folder, meta=meta)
            exact.setdefault((normalize_key(meta.artist), normalize_key(meta.title), meta.is_duet), []).append(entry)
            loose_artist = VERSION_KEY_PREFIX + loose_key(meta.artist)
            loose.setdefault((loose_artist, loose_key(meta.title), meta.is_duet), []).append(entry)
    return _Scan(
        groups=_build_groups(exact, is_version=False),
        version_groups=_build_groups(loose, is_version=True),
        empty_folders=sorted(empty, key=lambda f: f.folder.lower()),
    )


_cache_lock = threading.Lock()
_cache: _Scan | None = None
_cache_scanned_at: datetime | None = None


def _cached_scan() -> _Scan:
    """The cached scan, scanning the filesystem only once."""
    with _cache_lock:
        if _cache is not None:
            return _cache
    return refresh_cache()


def refresh_cache() -> _Scan:
    """Rescan the filesystem now and replace the cache."""
    global _cache, _cache_scanned_at
    scan = _scan_library()
    with _cache_lock:
        _cache = scan
        _cache_scanned_at = datetime.now(UTC)
    return scan


def last_scanned_at() -> datetime | None:
    with _cache_lock:
        return _cache_scanned_at


def _dismissed_keys(db: Session) -> set[tuple[str, str, bool]]:
    rows = db.scalars(select(DismissedDuplicate)).all()
    return {(r.artist_key, r.title_key, r.is_duet) for r in rows}


def find_duplicate_groups(db: Session) -> list[DuplicateGroup]:
    """Exact duplicate groups not yet dismissed by an admin."""
    dismissed = _dismissed_keys(db)
    return [g for g in _cached_scan().groups if (g.artist_key, g.title_key, g.is_duet) not in dismissed]


def find_version_groups(db: Session) -> list[DuplicateGroup]:
    """Possible duplicates (versions of a song) not yet dismissed by an admin."""
    dismissed = _dismissed_keys(db)
    return [g for g in _cached_scan().version_groups if (g.artist_key, g.title_key, g.is_duet) not in dismissed]


def find_empty_folders() -> list[EmptyFolder]:
    """Song folders without any UltraStar song file."""
    return _cached_scan().empty_folders


def get_duplicate_group(db: Session, group_id: str) -> DuplicateGroup | None:
    """Look up one exact or version group by id, dismissed or not (e.g. to
    review a past dismissal)."""
    scan = _cached_scan()
    for group in scan.groups + scan.version_groups:
        if group.group_id == group_id:
            return group
    return None


def is_dismissed(db: Session, group: DuplicateGroup) -> bool:
    row = db.scalar(
        select(DismissedDuplicate).where(
            DismissedDuplicate.artist_key == group.artist_key,
            DismissedDuplicate.title_key == group.title_key,
            DismissedDuplicate.is_duet == group.is_duet,
        )
    )
    return row is not None


def dismiss_group(db: Session, group: DuplicateGroup, dismissed_by: str) -> None:
    if is_dismissed(db, group):
        return
    db.add(
        DismissedDuplicate(
            artist_key=group.artist_key,
            title_key=group.title_key,
            is_duet=group.is_duet,
            dismissed_by_username=dismissed_by,
        )
    )
    db.commit()
