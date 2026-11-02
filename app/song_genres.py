"""About me: the song library's genres, as the song files name them - behind
the Genres page (app/routes/songs.py).

The USDX Song Factory writes normalised genres into the #GENRE tag of the
song files ("Symphonic, Metal"), so a value is only split at commas and
trimmed here (split_genre_tag); the Factory's placeholders for "no genre"
(PLACEHOLDERS, the same list as its genre_lookup.py) are left out. A song
folder's genres are those of every .txt directly in it, in file order, each
once (folder_genres).

The library scan (app/library_history.py) calls record_genres() for every
folder it sees and stores the result in SongGenre; a folder that is gone or
has no genre has no rows. genres_by_folder() and the functions after it are
what the Genres page reads.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .models import SongGenre
from .songs import Song
from .ultrastar import parse_header_tags, read_song_text

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


def folder_genres(folder: Path) -> list[str]:
    """The genres of every .txt directly in the folder, in file order, each once."""
    try:
        txt_files = sorted(p for p in folder.iterdir() if p.suffix.lower() == ".txt" and p.is_file())
    except OSError:
        return []
    tags = []
    for path in txt_files:
        try:
            tags.append(parse_header_tags(read_song_text(path)).get("GENRE", ""))
        except OSError:
            continue
    return split_genre_tag(",".join(tags))


def record_genres(db: Session, root: Path, folders: Iterable[str]) -> None:
    """Stores the genres of these folders - the whole library - and forgets
    those of every other folder. Leaves committing to the caller."""
    folders = list(folders)
    stored: dict[str, list[str]] = {}
    for row in db.scalars(select(SongGenre).order_by(SongGenre.position)):
        stored.setdefault(row.folder, []).append(row.genre)
    db.execute(delete(SongGenre).where(SongGenre.folder.not_in(folders)))
    for folder in folders:
        genres = folder_genres(root / folder)
        if genres == stored.get(folder, []):
            continue
        db.execute(delete(SongGenre).where(SongGenre.folder == folder))
        db.add_all(SongGenre(folder=folder, genre=genre, position=i) for i, genre in enumerate(genres))


def genres_by_folder(db: Session, songs: list[Song]) -> dict[str, list[str]]:
    """The genres of each of these songs that has one, in file order."""
    folders = {song.folder for song in songs}
    by_folder: dict[str, list[str]] = {}
    for folder, genre in db.execute(
        select(SongGenre.folder, SongGenre.genre).order_by(SongGenre.folder, SongGenre.position)
    ):
        if folder in folders:
            by_folder.setdefault(folder, []).append(genre)
    return by_folder


def search_with_genres(songs: list[Song], genres: dict[str, list[str]], query: str) -> list[Song]:
    """The songs with a genre matching every word of the query in their
    folder, band, title or genres, in library order."""
    terms = query.strip().lower().split()
    matches = []
    for song in songs:
        if song.folder not in genres:
            continue
        haystack = song.haystack + "\n" + "\n".join(genres[song.folder]).lower()
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
