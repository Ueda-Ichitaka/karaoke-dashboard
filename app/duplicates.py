"""About me: detects duplicate songs across the library for admin review.

Two UltraStar entries (each parsed from a .txt file, possibly in different
folders) are the same song if their artist and title match after
normalization and they agree on duet status - a duet arrangement and a solo
arrangement of the same song are an intentional variant, not a duplicate.
Groups of two or more matching entries are duplicates. Groups are computed
live from the filesystem on every call; an admin "dismisses" one by
recording its normalized key in the dismissed_duplicates table (see
app/models.py), which future lookups then skip.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import songs, ultrastar
from .models import DismissedDuplicate

_WHITESPACE = re.compile(r"\s+")

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


def _all_groups() -> list[DuplicateGroup]:
    """Every duplicate group in the library right now, dismissed or not."""
    buckets: dict[tuple[str, str, bool], list[DuplicateEntry]] = {}
    for song in songs.all_songs():
        for meta in ultrastar.scan_folder_songs(song.folder):
            key = (normalize_key(meta.artist), normalize_key(meta.title), meta.is_duet)
            buckets.setdefault(key, []).append(DuplicateEntry(folder=song.folder, meta=meta))

    groups = [
        DuplicateGroup(
            group_id=_group_id(*key),
            artist_key=key[0],
            title_key=key[1],
            is_duet=key[2],
            entries=sorted(entries, key=lambda e: (e.folder, e.meta.source_file)),
        )
        for key, entries in buckets.items()
        if len(entries) > 1
    ]
    groups.sort(key=lambda g: ((g.display_artist or "").lower(), g.display_title.lower()))
    return groups


def _dismissed_keys(db: Session) -> set[tuple[str, str, bool]]:
    rows = db.scalars(select(DismissedDuplicate)).all()
    return {(r.artist_key, r.title_key, r.is_duet) for r in rows}


def find_duplicate_groups(db: Session) -> list[DuplicateGroup]:
    """Duplicate groups not yet dismissed by an admin."""
    dismissed = _dismissed_keys(db)
    return [g for g in _all_groups() if (g.artist_key, g.title_key, g.is_duet) not in dismissed]


def get_duplicate_group(db: Session, group_id: str) -> DuplicateGroup | None:
    """Look up one group by id, dismissed or not (e.g. to review a past dismissal)."""
    for group in _all_groups():
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
