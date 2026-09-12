"""About me: flags a song sitting in the wrong folder - one whose own
#ARTIST/#TITLE tags don't match the "Artist - Title" its folder is named
after. Typically caused by a batch-import bug that dumped an unrelated
song's files into an otherwise correctly-named folder. Only folders whose
name itself parses as "Artist - Title" are considered (see
app/structure_check.py for folders that fail even that), and only songs
that carry both tags (see app/format_check.py for songs missing them).

The comparison ignores parenthesized/bracketed asides and a couple of known
noise suffixes (e.g. a record label pulled in from a source video's title),
and treats filename-unsafe characters - and the "-"/"|" that commonly
replace them - as interchangeable: a real ":" or "/" in a tag is often
dropped or swapped for a dash once it becomes part of a folder/file name,
which would otherwise look like a mismatch even though it's the same song.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .config import settings
from .duplicates import normalize_key
from .songs import parse_folder
from .ultrastar import parse_song_file

_BRACKETED_RE = re.compile(r"\([^)]*\)|\[[^\]]*\]")
_NOISE_SUBSTRINGS = ("napalm records",)
_FILENAME_UNSAFE_RE = re.compile(r'[\\/:*?"<>|-]')


def _comparison_key(text: str) -> str:
    cleaned = _BRACKETED_RE.sub(" ", text)
    lowered = cleaned.casefold()
    for noise in _NOISE_SUBSTRINGS:
        lowered = lowered.replace(noise, " ")
    lowered = _FILENAME_UNSAFE_RE.sub(" ", lowered)
    return normalize_key(lowered)


@dataclass(frozen=True, slots=True)
class MisplacedSong:
    folder: str
    source_file: str
    artist: str
    title: str
    expected_folder: str  # best-guess "Artist - Title" this song actually belongs in


def find_misplaced_songs(root: str | Path | None = None) -> list[MisplacedSong]:
    base = Path(root if root is not None else settings.songs_dir)
    ignore = set(settings.song_ignore_names)
    results: list[MisplacedSong] = []

    try:
        entries = sorted(base.iterdir())
    except OSError:
        return []

    for folder in entries:
        if not folder.is_dir() or folder.name.startswith(".") or folder.name in ignore:
            continue

        parsed = parse_folder(folder.name)
        if parsed.artist is None:
            continue  # non-conforming folder name - structure_check's concern, not this one

        expected_artist_key = _comparison_key(parsed.artist)
        expected_title_key = _comparison_key(parsed.title)

        songs = (parse_song_file(p) for p in sorted(folder.glob("*.txt")))
        for meta in (m for m in songs if m is not None):
            if not meta.artist or not meta.title:
                continue  # can't judge placement without both tags
            artist_matches = _comparison_key(meta.artist) == expected_artist_key
            title_matches = _comparison_key(meta.title) == expected_title_key
            if artist_matches and title_matches:
                continue  # correctly placed
            results.append(
                MisplacedSong(
                    folder=folder.name,
                    source_file=meta.source_file,
                    artist=meta.artist,
                    title=meta.title,
                    expected_folder=f"{meta.artist}{settings.song_separator}{meta.title}",
                )
            )
    return results
