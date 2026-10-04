"""About me: builds the NUL-delimited move lists that the standalone
scripts/apply_moves.sh script (outside app/, never shipped in the
container) consumes to actually relocate misplaced songs and non-
conforming nested subfolders on disk - something UltraStar Manager's own
.upl playlist export can point an admin at but never do itself, since it
has no file-move feature. Replaces the old .upl export for these two
integrity-view sections only (see app/upl_export.py, still used for the
song-file-format-issues section, which needs no moving).

Format: a flat stream of NUL-terminated tokens, alternating a source path
then its destination path - the same convention as `find -print0`. No
other separator or escaping is needed, since a NUL byte can never appear
in a real filename; the script reads it with a `read -d ''` loop.
"""

from __future__ import annotations

from pathlib import Path

from .config import settings
from .misplaced_check import MisplacedSong
from .structure_check import StructureIssue
from .ultrastar import parse_header_tags, read_song_text

# Tags that can reference a song's own files, beyond the .txt file itself -
# same media tags app/ultrastar.py checks, plus the cover image.
_OWN_FILE_TAGS = ("AUDIO", "MP3", "VIDEO", "COVER")

# A nested subfolder exactly named "-" is deliberately left alone, never
# moved - see app/move_export.py callers (app/routes/admin.py).
IGNORED_NESTED_FOLDER = "-"


def sanitize_folder_component(name: str) -> str:
    """A folder name can't contain "/" (e.g. the band "AC/DC") - replace it
    with "-", the same substitution a real "/" or ":" already gets when it
    would otherwise land in a folder name (see app/misplaced_check.py).
    """
    return name.replace("/", "-")


def _encode(tokens: list[str]) -> bytes:
    return "".join(token + "\x00" for token in tokens).encode("utf-8")


def _own_files(folder: Path, txt_filename: str) -> list[str]:
    """The .txt file plus whichever of its own media/cover files exist."""
    tags = parse_header_tags(read_song_text(folder / txt_filename))
    names = [txt_filename]
    for tag in _OWN_FILE_TAGS:
        name = tags.get(tag)
        if name and (folder / name).is_file():
            names.append(name)
    return names


def build_misplaced_moves(songs: list[MisplacedSong], root: str | Path | None = None) -> bytes:
    base = Path(root if root is not None else settings.songs_dir)
    tokens: list[str] = []
    for song in songs:
        source_folder = base / song.folder
        artist = sanitize_folder_component(song.artist)
        title = sanitize_folder_component(song.title)
        dest_folder = base / f"{artist}{settings.song_separator}{title}"
        for name in _own_files(source_folder, song.source_file):
            tokens.append(str(source_folder / name))
            tokens.append(str(dest_folder / name))
    return _encode(tokens)


def build_structure_moves(issues: list[StructureIssue], root: str | Path | None = None) -> bytes:
    base = Path(root if root is not None else settings.songs_dir)
    ignore = set(settings.song_ignore_names) | {IGNORED_NESTED_FOLDER}
    tokens: list[str] = []
    for issue in issues:
        folder = base / issue.folder
        try:
            children = sorted(p for p in folder.iterdir() if p.is_dir() and p.name not in ignore)
        except OSError:
            continue
        for child in children:
            tokens.append(str(child))
            tokens.append(str(base / child.name))
    return _encode(tokens)
