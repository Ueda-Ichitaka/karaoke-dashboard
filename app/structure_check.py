"""About me: flags song folders that don't follow the library's flat
"Artist - Title" convention (a folder may hold several songs, but not
nested subfolders), for the admin integrity view's structure report. Some
non-conformance is introduced by other library-management tools. See also
app/songs.py: parse_folder(), which this reuses to detect a diverging name.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .config import settings
from .songs import parse_folder

_MAX_TREE_LINES = 200


@dataclass(frozen=True, slots=True)
class StructureIssue:
    folder: str
    reasons: list[str] = field(default_factory=list)


def _nested_subfolders(folder: Path) -> list[str]:
    try:
        return sorted(child.name for child in folder.iterdir() if child.is_dir())
    except OSError:
        return []


def check_structure(root: str | Path | None = None) -> list[StructureIssue]:
    base = Path(root if root is not None else settings.songs_dir)
    ignore = set(settings.song_ignore_names)
    issues = []
    try:
        entries = sorted(base.iterdir())
    except OSError:
        return []
    for folder in entries:
        if not folder.is_dir() or folder.name.startswith(".") or folder.name in ignore:
            continue

        reasons = []
        if parse_folder(folder.name).artist is None:
            reasons.append('Folder name does not follow the "Artist - Title" convention.')
        nested = _nested_subfolders(folder)
        if nested:
            reasons.append(f"Contains nested subfolder(s): {', '.join(nested)}.")
        if reasons:
            issues.append(StructureIssue(folder=folder.name, reasons=reasons))
    return issues


def folder_tree(folder_name: str, root: str | Path | None = None) -> list[str]:
    """An indented listing of one song folder's contents, for the report."""
    base = Path(root if root is not None else settings.songs_dir)
    top = base / folder_name
    lines: list[str] = []

    def walk(path: Path, prefix: str) -> None:
        try:
            children = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except OSError:
            return
        for child in children:
            if len(lines) >= _MAX_TREE_LINES:
                lines.append(prefix + "… (truncated)")
                return
            marker = "/" if child.is_dir() else ""
            lines.append(f"{prefix}{child.name}{marker}")
            if child.is_dir():
                walk(child, prefix + "  ")

    walk(top, "")
    return lines
