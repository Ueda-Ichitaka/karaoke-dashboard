"""About me: reads UltraStar Deluxe ".txt" song files.

A karaoke song folder holds zero, one, or several UltraStar .txt files (a
folder can bundle multiple distinct songs from a batch import). This module
parses the header tags of one such file into a SongMeta record, and scans a
folder for every song it contains. Results are cached in memory for
settings.scan_cache_seconds, mirroring the folder-index cache in songs.py.

A song's length is read from the audio/video file it actually plays back
(#AUDIO/#MP3/#VIDEO), not from the UltraStar #START/#END tags - those are
rarely present, and the media file's own duration is what the karaoke system
plays anyway.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path

import mutagen

from .config import settings

# The two tags every valid UltraStar file carries. Their absence means the
# .txt is not a song file (e.g. a stray readme dropped into the folder).
_MANDATORY_TAGS = ("BPM", "GAP")

# Tags that can reference the song's playback media, checked in this order:
# a dedicated audio file first, then the legacy #MP3 tag, then the video.
_MEDIA_TAGS = ("AUDIO", "MP3", "VIDEO")


@dataclass(frozen=True, slots=True)
class SongMeta:
    source_file: str
    title: str
    artist: str | None
    genre: str | None
    year: int | None
    language: str | None
    is_duet: bool
    duet_singers: tuple[str, str] | None
    length_seconds: float | None
    cover_file: str | None

    @property
    def length_display(self) -> str | None:
        if self.length_seconds is None:
            return None
        total = int(round(self.length_seconds))
        minutes, seconds = divmod(total, 60)
        return f"{minutes}:{seconds:02d}"


def parse_header_tags(text: str) -> dict[str, str]:
    """Parse the "# KEY : VALUE" header lines at the top of a song file."""
    tags: dict[str, str] = {}
    for line in text.splitlines():
        if not line.startswith("#"):
            break  # header ends at the first note/body line
        if ":" not in line:
            continue
        key, _, value = line[1:].partition(":")
        tags[key.strip().upper()] = value.strip()
    return tags


def read_song_text(path: Path) -> str:
    raw = path.read_bytes()[:2_000_000]  # small metadata files; cap defensively
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return raw.decode("cp1252")
        except UnicodeDecodeError:
            return raw.decode("utf-8", errors="replace")


def _media_file(tags: dict[str, str], folder: Path) -> Path | None:
    """Resolve the audio/video file this song actually plays back, if any."""
    for tag in _MEDIA_TAGS:
        name = tags.get(tag)
        if not name:
            continue
        candidate = folder / name
        if candidate.is_file():
            return candidate
    return None


def _length_seconds(tags: dict[str, str], folder: Path) -> float | None:
    media = _media_file(tags, folder)
    if media is None:
        return None
    try:
        info = mutagen.File(media)
    except Exception:
        return None  # unreadable/corrupt media file - no length, not a crash
    length = getattr(getattr(info, "info", None), "length", None)
    return float(length) if length else None


def _year(tags: dict[str, str]) -> int | None:
    raw = tags.get("YEAR", "")
    if raw.isdigit() and len(raw) == 4:
        return int(raw)
    return None


def _cover_file(tags: dict[str, str], folder: Path) -> str | None:
    name = tags.get("COVER")
    if not name:
        return None
    candidate = folder / name
    return candidate.name if candidate.is_file() else None


def parse_song_file(path: Path) -> SongMeta | None:
    """Parse one UltraStar .txt file, or return None if it isn't one."""
    tags = parse_header_tags(read_song_text(path))
    if not all(tag in tags for tag in _MANDATORY_TAGS):
        return None

    duet_p1 = tags.get("DUETSINGERP1") or None
    duet_p2 = tags.get("DUETSINGERP2") or None

    return SongMeta(
        source_file=path.name,
        title=tags.get("TITLE") or path.stem,
        artist=tags.get("ARTIST") or None,
        genre=tags.get("GENRE") or None,
        year=_year(tags),
        language=tags.get("LANGUAGE") or None,
        is_duet=bool(duet_p1 or duet_p2),
        duet_singers=(duet_p1, duet_p2) if duet_p1 and duet_p2 else None,
        length_seconds=_length_seconds(tags, path.parent),
        cover_file=_cover_file(tags, path.parent),
    )


class _MetaCache:
    """Per-folder SongMeta cache, TTL-based like the folder index in songs.py."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[float, list[SongMeta]]] = {}

    def get(self, folder_name: str) -> list[SongMeta]:
        now = time.monotonic()
        with self._lock:
            cached = self._entries.get(folder_name)
            if cached and (now - cached[0]) <= settings.scan_cache_seconds:
                return cached[1]
        metas = self._scan(folder_name)
        with self._lock:
            self._entries[folder_name] = (now, metas)
        return metas

    @staticmethod
    def _scan(folder_name: str) -> list[SongMeta]:
        folder = Path(settings.songs_dir) / folder_name
        try:
            txt_files = sorted(p for p in folder.iterdir() if p.suffix.lower() == ".txt")
        except OSError:
            return []
        metas = [parse_song_file(p) for p in txt_files]
        return [m for m in metas if m is not None]


_cache = _MetaCache()


def scan_folder_songs(folder_name: str) -> list[SongMeta]:
    """Return every UltraStar song found directly inside a song folder."""
    return _cache.get(folder_name)
