"""Scan the mounted songs directory and expose a searchable, cached listing."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass

from .config import settings


@dataclass(frozen=True, slots=True)
class Song:
    folder: str          # raw folder name on disk
    artist: str | None   # best-effort parse
    title: str           # best-effort parse (falls back to the raw folder name)

    @property
    def display(self) -> str:
        if self.artist:
            return f"{self.artist} - {self.title}"
        return self.title

    @property
    def haystack(self) -> str:
        return f"{self.folder}\n{self.artist or ''}\n{self.title}".lower()


@dataclass(frozen=True, slots=True)
class Page:
    items: list[Song]
    total: int
    page: int
    pages: int
    page_size: int

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.pages


def parse_folder(name: str) -> Song:
    sep = settings.song_separator
    if sep and sep in name:
        artist, title = name.split(sep, 1)
        artist = artist.strip()
        title = title.strip()
        if artist and title:
            return Song(folder=name, artist=artist, title=title)
    return Song(folder=name, artist=None, title=name.strip())


class _SongIndex:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._songs: list[Song] = []
        self._loaded_at: float = 0.0

    def _scan(self) -> list[Song]:
        root = settings.songs_dir
        ignore = set(settings.song_ignore_names)
        songs: list[Song] = []
        try:
            entries = os.scandir(root)
        except FileNotFoundError:
            print(f"[songs] directory not found: {root}")
            return []
        except PermissionError:
            print(f"[songs] permission denied: {root}")
            return []
        with entries:
            for entry in entries:
                name = entry.name
                if name.startswith(".") or name in ignore:
                    continue
                try:
                    if not entry.is_dir():
                        continue
                except OSError:
                    continue
                songs.append(parse_folder(name))
        songs.sort(key=lambda s: ((s.artist or s.title).lower(), s.title.lower()))
        return songs

    def all(self) -> list[Song]:
        now = time.monotonic()
        with self._lock:
            if not self._songs or (now - self._loaded_at) > settings.scan_cache_seconds:
                self._songs = self._scan()
                self._loaded_at = now
            return self._songs

    def refresh(self) -> None:
        with self._lock:
            self._songs = self._scan()
            self._loaded_at = time.monotonic()


_index = _SongIndex()


def _filter(songs: list[Song], query: str) -> list[Song]:
    query = query.strip().lower()
    if not query:
        return songs
    terms = query.split()
    return [s for s in songs if all(term in s.haystack for term in terms)]


def search(query: str = "", page: int = 1, page_size: int | None = None) -> Page:
    page_size = page_size or settings.page_size
    matches = _filter(_index.all(), query)
    total = len(matches)
    pages = max(1, (total + page_size - 1) // page_size)
    page = max(1, min(page, pages))
    start = (page - 1) * page_size
    return Page(
        items=matches[start : start + page_size],
        total=total,
        page=page,
        pages=pages,
        page_size=page_size,
    )


def all_songs() -> list[Song]:
    return _index.all()


def get_by_folder(folder: str) -> Song | None:
    for song in _index.all():
        if song.folder == folder:
            return song
    return None


def total_count() -> int:
    return len(_index.all())


def refresh() -> None:
    _index.refresh()
