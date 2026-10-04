"""About me: builds an UltraStar Deluxe Playlist (.upl) file scoped to the
songs the admin integrity view's song-file-format check has flagged (see
app/format_check.py), so an admin can open it in UltraStar Manager
(third_party/ultrastar-manager, a submodule kept only for reference) and
jump straight to just those songs instead of the whole library. The
structure/misplaced-songs sections used to export this format too, but
UltraStar Manager has no way to actually move a file, so those two now
export a move list instead (app/move_export.py) for scripts/apply_moves.sh
to act on.

The .upl format and its "#Artist : Title" entry syntax come from that
project's own src/playlist/QUPlaylistFile.cpp - entries are matched by
Artist + Title, not by file path, so a song missing those tags can't get a
usable line here and is skipped.
"""

from __future__ import annotations

from pathlib import Path

from .config import settings
from .format_check import FileReport
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


def build_format_issues_upl(reports: list[FileReport], root: str | Path | None = None) -> str:
    base = Path(root if root is not None else settings.songs_dir)

    entries: list[tuple[str, str]] = []
    for report in reports:
        meta = parse_song_file(base / report.folder / report.filename)
        if meta and meta.artist and meta.title:
            entries.append((meta.artist, meta.title))

    return _render("Song file format issues", entries)
