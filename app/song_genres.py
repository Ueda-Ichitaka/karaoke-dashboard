"""About me: the song library's genres, as the song files name them - behind
the Genres page (app/routes/songs.py).

The USDX Song Factory writes normalised genres into the #GENRE tag of the
song files ("Symphonic, Metal"), so a value is only split at commas and
trimmed here (split_genre_tag); the Factory's placeholders for "no genre"
(PLACEHOLDERS, the same list as its genre_lookup.py) are left out. A song
folder's genres are those of every song file directly in it, in file order,
each once (folder_genres). A song file is a .txt the UltraStar parser
accepts (app/ultrastar.py: is_song_tags - it has #BPM) and not one of the
Factory's helper files (is_helper_file: language.txt, lyrics.txt, ...),
which are skipped unread; any other .txt beside it, a readme, never counts
either (song_files).

The library scan (app/library_history.py) calls record_genres() for every
folder it sees and stores the result in SongGenre; a folder that is gone or
has no genre has no rows.

A contributor can change a folder's genres on the Genres page's Edit tab
(save_genre_edit, reset_genre_edit): the edit (GenreEdit) stands in for the
folder's file genres everywhere on the Genres page (genres_by_folder) until
a library scan reads the same genres from the files, which ends it. The
Edit tab's export (genre_edit_lines) lists every open edit for the USDX
Song Factory: per song file of the folder, its path relative to the
library root and the genres, tab-separated.

genres_by_folder() and the functions after it are what the Genres page
reads.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .models import GenreEdit, SongGenre
from .songs import Song
from .ultrastar import is_helper_file, is_song_tags, parse_header_tags, read_song_text

PLACEHOLDERS = frozenset({"unknown", "no idea", "other", "none", "misc"})
GENRE_MAX_LENGTH = 128  # SongGenre.genre


def split_genre_tag(value: str | None) -> list[str]:
    """The genres of a #GENRE value: split at commas, trimmed, without empty
    parts, placeholders and repeats (any case; the first spelling stays)."""
    genres: list[str] = []
    seen: set[str] = set()
    for part in (value or "").split(","):
        genre = part.strip()[:GENRE_MAX_LENGTH]
        key = genre.casefold()
        if genre and key not in PLACEHOLDERS and key not in seen:
            seen.add(key)
            genres.append(genre)
    return genres


def _same(one: list[str], other: list[str]) -> bool:
    """The same genres in the same order, in any case."""
    return [genre.casefold() for genre in one] == [genre.casefold() for genre in other]


def _song_file_tags(folder: Path) -> list[tuple[Path, dict[str, str]]]:
    """Each song file directly in the folder with its header tags, by name."""
    try:
        txt_files = sorted(p for p in folder.iterdir()
                           if p.suffix.lower() == ".txt" and not is_helper_file(p.name) and p.is_file())
    except OSError:
        return []
    found = []
    for path in txt_files:
        try:
            tags = parse_header_tags(read_song_text(path))
        except OSError:
            continue
        if is_song_tags(tags):
            found.append((path, tags))
    return found


def song_files(folder: Path) -> list[Path]:
    """The song files directly in the folder, by name - no other .txt."""
    return [path for path, _ in _song_file_tags(folder)]


def folder_genres(folder: Path) -> list[str]:
    """The genres of every song file directly in the folder, in file order, each once."""
    return split_genre_tag(",".join(tags.get("GENRE", "") for _, tags in _song_file_tags(folder)))


def record_genres(db: Session, root: Path, folders: Iterable[str]) -> None:
    """Stores the genres of these folders - the whole library - and forgets
    those of every other folder; ends every edit whose folder's files now
    name the same genres. Leaves committing to the caller."""
    folders = list(folders)
    stored: dict[str, list[str]] = {}
    for row in db.scalars(select(SongGenre).order_by(SongGenre.position)):
        stored.setdefault(row.folder, []).append(row.genre)
    edits = {edit.folder: edit for edit in db.scalars(select(GenreEdit))}
    db.execute(delete(SongGenre).where(SongGenre.folder.not_in(folders)))
    for folder in folders:
        genres = folder_genres(root / folder)
        if folder in edits and _same(split_genre_tag(edits[folder].genres), genres):
            db.delete(edits[folder])
        if genres == stored.get(folder, []):
            continue
        db.execute(delete(SongGenre).where(SongGenre.folder == folder))
        db.add_all(SongGenre(folder=folder, genre=genre, position=i) for i, genre in enumerate(genres))


def file_genres_by_folder(db: Session, songs: list[Song]) -> dict[str, list[str]]:
    """The genres the song files name for each of these songs that has one, in file order."""
    folders = {song.folder for song in songs}
    by_folder: dict[str, list[str]] = {}
    for folder, genre in db.execute(
        select(SongGenre.folder, SongGenre.genre).order_by(SongGenre.folder, SongGenre.position)
    ):
        if folder in folders:
            by_folder.setdefault(folder, []).append(genre)
    return by_folder


def folder_file_genres(db: Session, folder: str) -> list[str]:
    """The genres the song files of one folder name, in file order."""
    return list(db.scalars(select(SongGenre.genre).where(SongGenre.folder == folder).order_by(SongGenre.position)))


def open_edits(db: Session) -> dict[str, GenreEdit]:
    """Every open genre edit, by folder."""
    return {edit.folder: edit for edit in db.scalars(select(GenreEdit).order_by(GenreEdit.folder))}


def genres_by_folder(db: Session, songs: list[Song]) -> dict[str, list[str]]:
    """The genres of each of these songs that has one, in file order - an
    open edit's instead of the files'."""
    by_folder = file_genres_by_folder(db, songs)
    folders = {song.folder for song in songs}
    for folder, edit in open_edits(db).items():
        if folder in folders:
            by_folder[folder] = split_genre_tag(edit.genres)
    return by_folder


def current_genres(db: Session, folder: str) -> list[str]:
    """One folder's genres as the Genres page shows them: its open edit's, else its files'."""
    edit = db.scalar(select(GenreEdit).where(GenreEdit.folder == folder))
    return split_genre_tag(edit.genres) if edit is not None else folder_file_genres(db, folder)


def edited_genres(text: str) -> list[str]:
    """The genres a contributor typed: split like a #GENRE value, each with
    its runs of white space (tabs too) made one space. Raises ValueError
    when no genre is left."""
    genres = split_genre_tag(",".join(" ".join(part.split()) for part in text.split(",")))
    if not genres:
        raise ValueError("Enter at least one genre.")
    return genres


def save_genre_edit(db: Session, folder: str, text: str, username: str) -> list[str]:
    """Sets a folder's genres from what a contributor typed (edited_genres):
    the same as its files name ends its edit, anything else is the edit.
    Returns the genres the folder has now. Commits."""
    genres = edited_genres(text)
    file_genres = folder_file_genres(db, folder)
    edit = db.scalar(select(GenreEdit).where(GenreEdit.folder == folder))
    if _same(genres, file_genres):
        if edit is not None:
            db.delete(edit)
        db.commit()
        return file_genres
    if edit is None:
        edit = GenreEdit(folder=folder, genres="", edited_by=username)
        db.add(edit)
    edit.genres, edit.edited_by, edit.edited_at = ", ".join(genres), username, datetime.now(UTC)
    db.commit()
    return genres


def reset_genre_edit(db: Session, folder: str) -> None:
    """Ends a folder's edit - back to the genres its files name. Commits."""
    db.execute(delete(GenreEdit).where(GenreEdit.folder == folder))
    db.commit()


def genre_edit_lines(db: Session, root: Path) -> str:
    """The export of every open edit: per song file of the folder, its path
    relative to the library root, a tab and the genres - one line each, by
    folder and file name."""
    lines = []
    for folder, edit in open_edits(db).items():
        for path in song_files(root / folder):
            lines.append(f"{folder}/{path.name}\t{', '.join(split_genre_tag(edit.genres))}\n")
    return "".join(lines)


def search_with_genres(songs: list[Song], genres: dict[str, list[str]], query: str,
                       with_genre_only: bool = True) -> list[Song]:
    """The songs matching every word of the query in their folder, band,
    title or genres, in library order - only those with a genre unless
    with_genre_only is False."""
    terms = query.strip().lower().split()
    matches = []
    for song in songs:
        if with_genre_only and song.folder not in genres:
            continue
        haystack = song.haystack + "\n" + "\n".join(genres.get(song.folder, [])).lower()
        if all(term in haystack for term in terms):
            matches.append(song)
    return matches


def genre_counts(songs: list[Song], genres: dict[str, list[str]]) -> list[tuple[str, int]]:
    """Each genre of these songs with its number of songs, most songs first,
    then by name."""
    counts = Counter(genre for song in songs for genre in genres.get(song.folder, []))
    return sorted(counts.items(), key=lambda item: (-item[1], item[0].casefold()))


def companions(songs: list[Song], genres: dict[str, list[str]], genre: str, limit: int = 3) -> list[tuple[str, int]]:
    """The genres the songs of one genre share most, with their numbers of
    songs - at most limit of them."""
    with_genre = [song for song in songs if genre in genres.get(song.folder, [])]
    return [item for item in genre_counts(with_genre, genres) if item[0] != genre][:limit]
