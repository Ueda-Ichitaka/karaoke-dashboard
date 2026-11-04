"""Tests for app/library_history.py: the library scan behind the "Recently
added" and "Recently updated" lists on /songs.

The very first scan (nothing recorded yet) counts every folder as old. After
that, a new folder following the flat "Artist - Title" convention is a new
song, dated by the scan that first sees it, and a write to a .txt, .mp3 or
.opus file directly in a folder is an update, dated by the file's write
time - except writes within the grace period after a new folder was first
seen, which are part of adding it. A reset forgets everything and scans
again as a very first scan. Every scan, the first included, also records
each folder's newest song-file write - what the "is it fixed" checks compare
a report's time with.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.database import SessionLocal
from app.library_history import (
    ADD_GRACE,
    last_writes,
    recent_additions,
    recent_updates,
    reset_library,
    scan_library,
)
from app.songs import parse_folder

NOW = datetime(2026, 10, 18, 11, 0, tzinfo=UTC)
LATER = datetime(2026, 10, 19, 11, 0, tzinfo=UTC)
OLD = datetime(2025, 1, 1, tzinfo=UTC)
SINCE = datetime(2026, 8, 1, tzinfo=UTC)


def _write(path: Path, when: datetime, content: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    os.utime(path, (when.timestamp(), when.timestamp()))


def _scan(root: Path, now: datetime) -> None:
    with SessionLocal() as db:
        scan_library(db, root=root, now=now)


def _library(root: Path):
    return [parse_folder(name) for name in os.listdir(root)]


def _added(root: Path) -> list[tuple[str, str]]:
    with SessionLocal() as db:
        return [(s.folder, d.strftime("%Y-%m-%d")) for s, d in recent_additions(db, _library(root), SINCE)]


def _updated(root: Path) -> list[tuple[str, str]]:
    with SessionLocal() as db:
        return [(s.folder, d.strftime("%Y-%m-%d %H:%M")) for s, d in recent_updates(db, _library(root), SINCE)]


@pytest.fixture()
def root(tmp_path, fresh_db) -> Path:
    """A library whose first scan has run, with one old song in it."""
    _write(tmp_path / "Old - Song" / "song.txt", OLD)
    _scan(tmp_path, NOW - timedelta(days=30))
    return tmp_path


def test_the_first_scan_counts_every_folder_as_old(tmp_path, fresh_db):
    _write(tmp_path / "A - One" / "song.txt", NOW - timedelta(hours=1))
    _scan(tmp_path, NOW)
    assert _added(tmp_path) == []
    assert _updated(tmp_path) == []


def test_a_new_folder_following_the_convention_is_a_new_song(root):
    _write(root / "B - Two" / "song.txt", OLD)
    _scan(root, NOW)
    assert _added(root) == [("B - Two", "2026-10-18")]


def test_a_new_folder_breaking_the_convention_is_not_listed_until_it_follows_it(root):
    _write(root / "NoSeparator" / "song.txt", OLD)
    _write(root / "C - Nested" / "CD1" / "song.txt", OLD)
    _write(root / "D - Thumbs" / "@eaDir" / "thumb.jpg", OLD)  # NAS bookkeeping, not nesting
    _scan(root, NOW)
    assert _added(root) == [("D - Thumbs", "2026-10-18")]

    (root / "C - Nested" / "CD1" / "song.txt").rename(root / "C - Nested" / "song.txt")
    (root / "C - Nested" / "CD1").rmdir()
    _scan(root, LATER)
    assert _added(root) == [("C - Nested", "2026-10-18"), ("D - Thumbs", "2026-10-18")]


@pytest.mark.parametrize("name", ["song.txt", "song.mp3", "Song.OPUS"])
def test_a_write_to_a_song_txt_mp3_or_opus_is_an_update(root, name):
    folder = root / "Old - Song"
    _write(folder / name, OLD)
    _write(folder / "cover.jpg", OLD)
    _scan(root, NOW)
    assert _updated(root) == []  # any change is dated by its write time, here long ago

    _write(folder / name, NOW + timedelta(hours=2), "changed")
    _scan(root, LATER)
    assert _updated(root) == [("Old - Song", "2026-10-18 13:00")]


def test_other_files_and_deletions_are_not_updates(root):
    folder = root / "Old - Song"
    _write(folder / "song.mp3", OLD)
    _scan(root, NOW)
    _updated_before = _updated(root)

    _write(folder / "cover.jpg", NOW)
    _write(folder / "song.avi", NOW)
    (folder / "song.mp3").unlink()
    _scan(root, LATER)
    assert _updated(root) == _updated_before


def test_a_replaced_file_counts_even_when_older_than_the_newest_file(tmp_path, fresh_db):
    folder = tmp_path / "Old - Song"
    _write(folder / "song.txt", NOW - timedelta(days=5))
    _write(folder / "song.mp3", OLD)
    _scan(tmp_path, NOW)
    copied = NOW - timedelta(days=10)  # a copy that kept the original file time
    _write(folder / "song.mp3", copied, "repaired")
    _scan(tmp_path, LATER)
    assert _updated(tmp_path) == [("Old - Song", copied.strftime("%Y-%m-%d %H:%M"))]


def test_writes_within_the_grace_period_are_part_of_adding_a_new_song(root):
    folder = root / "B - Two"
    _write(folder / "song.txt", NOW)
    _scan(root, NOW)
    _write(folder / "song.mp3", NOW + ADD_GRACE - timedelta(minutes=1))
    _scan(root, NOW + timedelta(hours=2))
    assert _updated(root) == []

    _write(folder / "song.txt", NOW + ADD_GRACE + timedelta(minutes=1), "changed")
    _scan(root, LATER)
    assert _updated(root) == [("B - Two", (NOW + ADD_GRACE + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M"))]


def test_the_update_date_never_goes_back(root):
    folder = root / "Old - Song"
    _write(folder / "song.txt", NOW - timedelta(days=1), "first")
    _scan(root, NOW)
    _write(folder / "song.txt", NOW - timedelta(days=3), "second")
    _scan(root, LATER)
    assert _updated(root) == [("Old - Song", (NOW - timedelta(days=1)).strftime("%Y-%m-%d %H:%M"))]


def test_recent_lists_are_newest_first_and_only_hold_library_songs(root):
    _write(root / "A - One" / "song.txt", OLD)
    _write(root / "B - Two" / "song.txt", OLD)
    _write(root / "Gone - Song" / "song.txt", OLD)
    _scan(root, NOW - timedelta(days=1))
    for name, when in (("A - One", NOW - timedelta(hours=3)), ("B - Two", NOW - timedelta(hours=1)),
                       ("Gone - Song", NOW)):
        _write(root / name / "song.txt", when, "changed")
    _scan(root, NOW)
    for path in (root / "Gone - Song").iterdir():
        path.unlink()
    (root / "Gone - Song").rmdir()

    assert [folder for folder, _ in _updated(root)] == ["B - Two", "A - One"]
    assert [folder for folder, _ in _added(root)] == ["A - One", "B - Two"]


def test_updates_older_than_since_are_not_listed(root):
    _write(root / "Old - Song" / "song.mp3", SINCE - timedelta(days=1))
    _scan(root, NOW)
    assert _updated(root) == []


def test_reset_forgets_everything_and_scans_as_a_very_first_scan(root):
    _write(root / "B - Two" / "song.txt", OLD)
    _scan(root, NOW)
    _write(root / "Old - Song" / "song.txt", NOW, "changed")
    _scan(root, LATER)
    assert _added(root) and _updated(root)

    with SessionLocal() as db:
        reset_library(db, root=root, now=LATER)
    assert _added(root) == []
    assert _updated(root) == []


def test_reset_keeps_the_history_when_the_library_cannot_be_read(root, tmp_path_factory):
    _write(root / "B - Two" / "song.txt", OLD)
    _scan(root, NOW)
    with SessionLocal() as db:
        reset_library(db, root=tmp_path_factory.mktemp("unmounted"), now=LATER)
    assert _added(root) == [("B - Two", "2026-10-18")]


# ---- the newest song-file write, recorded from the very first scan on ----
def _last_writes(*folders: str) -> dict[str, str]:
    with SessionLocal() as db:
        return {f: d.strftime("%Y-%m-%d %H:%M") for f, d in last_writes(db, set(folders)).items()}


def test_the_first_scan_already_records_the_newest_song_file_write(tmp_path, fresh_db):
    folder = tmp_path / "A - One"
    _write(folder / "song.txt", NOW - timedelta(days=3))
    _write(folder / "song.opus", NOW - timedelta(days=1))
    _write(folder / "cover.jpg", NOW)
    _write(tmp_path / "Empty - Folder" / "cover.jpg", NOW)
    _scan(tmp_path, NOW)
    assert _updated(tmp_path) == []  # still nothing "recently updated" after the first scan
    assert _last_writes("A - One", "Empty - Folder") == {
        "A - One": (NOW - timedelta(days=1)).strftime("%Y-%m-%d %H:%M")}


def test_later_scans_move_the_newest_write_forward_never_back(root):
    folder = root / "Old - Song"
    _write(folder / "song.mp3", NOW - timedelta(hours=5))
    _scan(root, NOW)
    assert _last_writes("Old - Song") == {"Old - Song": (NOW - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M")}
    (folder / "song.mp3").unlink()
    _scan(root, LATER)
    assert _last_writes("Old - Song") == {"Old - Song": (NOW - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M")}


def test_a_detected_change_counts_as_a_write_too(root):
    folder = root / "Old - Song"
    _write(folder / "song.txt", NOW - timedelta(days=5))
    _write(folder / "song.mp3", OLD)
    _scan(root, NOW)
    _write(folder / "song.mp3", NOW - timedelta(days=4), "replaced")  # kept an older time than the .txt
    (folder / "song.txt").unlink()
    _scan(root, LATER)
    assert _last_writes("Old - Song") == {"Old - Song": (NOW - timedelta(days=4)).strftime("%Y-%m-%d %H:%M")}


@pytest.mark.parametrize("name", ["language.txt", "lyrics.txt", "Song_End.txt", "anchors.txt"])
def test_a_write_to_a_factory_helper_file_is_not_an_update(root, name):
    folder = root / "Old - Song"
    _write(folder / name, OLD)
    _scan(root, NOW)
    _write(folder / name, NOW + timedelta(hours=2), "changed")
    _scan(root, LATER)
    assert _updated(root) == []
