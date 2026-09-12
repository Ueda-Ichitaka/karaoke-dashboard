"""About me: builds UltraStar Deluxe Playlist (.upl) files scoped to songs
the admin integrity view has flagged as problems (see app/structure_check.py
and app/misplaced_check.py), so an admin can open one in UltraStar Manager
(third_party/ultrastar-manager, a submodule kept only for reference) and
jump straight to just those songs instead of the whole library.

The .upl format and its "#Artist : Title" entry syntax come from that
project's own src/playlist/QUPlaylistFile.cpp - entries are matched by
Artist + Title, not by file path, so a song missing those tags can't get a
usable line here and is skipped.
"""

from __future__ import annotations

from pathlib import Path

from .config import settings
from .misplaced_check import MisplacedSong
from .structure_check import StructureIssue
from .ultrastar import parse_song_file


def _render(playlist_name: str, entries: list[tuple[str, str]]) -> str:
    lines = [
        "######################################",
        "#Ultrastar Deluxe Playlist Format v1.0",
        f"Playlist {playlist_name} with {len(entries)} Songs.",
        "######################################",
        f"#Name: {playlist_name}",
        "#Songs:",
        *(f"{artist} : {title}" for artist, title in entries),
    ]
    return "\n".join(lines) + "\n"


def build_upl(issues: list[StructureIssue], root: str | Path | None = None) -> str:
    base = Path(root if root is not None else settings.songs_dir)

    entries: list[tuple[str, str]] = []
    for issue in issues:
        folder = base / issue.folder
        for txt_file in sorted(folder.rglob("*.txt")):
            meta = parse_song_file(txt_file)
            if meta and meta.artist and meta.title:
                entries.append((meta.artist, meta.title))

    return _render("Non-conforming folders", entries)


def build_misplaced_upl(songs: list[MisplacedSong]) -> str:
    entries = [(s.artist, s.title) for s in songs]
    return _render("Misplaced songs", entries)
