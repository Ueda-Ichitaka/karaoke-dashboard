"""Tests for app/song_genres.py: each song folder's genres, read from the
#GENRE tag of its song files by the library scan (app/library_history.py)
and stored in SongGenre.

The song files hold normalised genres (the USDX Song Factory writes them),
so a #GENRE value is only split at commas and trimmed; the placeholders the
Factory uses for "no genre" (Unknown, No idea, Other, None, Misc - any case)
are left out. A folder's genres are those of every song file directly in
it, in file order, each once - a .txt beside them that is no song file
(language.txt, lyrics.txt, a readme) never counts.

The export of the open genre edits lists those same song files.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.database import SessionLocal
from app.library_history import scan_library
from app.models import GenreEdit, SongGenre
from app.song_genres import folder_genres, genre_edit_lines, song_files, split_genre_tag


def _song(folder: Path, name: str, genre: str | None) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    genre_line = f"#GENRE:{genre}\n" if genre is not None else ""
    (folder / name).write_text(f"#TITLE:T\n#ARTIST:A\n{genre_line}#BPM:100\n#GAP:0\n: 0 1 0 La\nE\n",
                               encoding="utf-8")


def _stored(folder: str | None = None) -> dict[str, list[str]]:
    with SessionLocal() as db:
        rows = db.scalars(select(SongGenre).order_by(SongGenre.folder, SongGenre.position)).all()
    stored: dict[str, list[str]] = {}
    for row in rows:
        stored.setdefault(row.folder, []).append(row.genre)
    return stored if folder is None else stored.get(folder, [])


@pytest.mark.parametrize(("value", "genres"), [
    ("Metal", ["Metal"]),
    ("Symphonic, Metal", ["Symphonic", "Metal"]),
    (" Folk ,Metal,, ", ["Folk", "Metal"]),
    ("", []),
    (None, []),
    ("Unknown", []),
    ("no idea", []),
    ("Other, Misc, NONE", []),
    ("Unknown, Rock", ["Rock"]),
    ("Metal, metal, Folk", ["Metal", "Folk"]),
])
def test_split_genre_tag(value, genres):
    assert split_genre_tag(value) == genres


def test_a_folder_has_the_genres_of_all_its_song_files_each_once(tmp_path):
    _song(tmp_path, "a.txt", "Pop")
    _song(tmp_path, "b.txt", "Rock, Pop")
    assert folder_genres(tmp_path) == ["Pop", "Rock"]


def test_files_without_a_genre_and_other_files_add_nothing(tmp_path):
    _song(tmp_path, "a.txt", None)
    _song(tmp_path, "b.txt", "Unknown")
    (tmp_path / "notes.md").write_text("#GENRE:Jazz\n", encoding="utf-8")
    _song(tmp_path / "CD1", "nested.txt", "Jazz")
    assert folder_genres(tmp_path) == []


def test_a_cp1252_song_file_is_read(tmp_path):
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "a.txt").write_bytes("#TITLE:T\n#GENRE:Volksmusik, Schlagerä\n#BPM:1\n#GAP:0\nE\n"
                                     .encode("cp1252"))
    assert folder_genres(tmp_path) == ["Volksmusik", "Schlagerä"]


def test_an_unreadable_folder_has_no_genres(tmp_path):
    assert folder_genres(tmp_path / "missing") == []


def test_the_scan_stores_each_folders_genres_in_file_order(tmp_path, fresh_db):
    _song(tmp_path / "A - One", "one.txt", "Symphonic, Metal")
    _song(tmp_path / "B - Two", "two.txt", "Pop")
    with SessionLocal() as db:
        scan_library(db, root=tmp_path)
    assert _stored() == {"A - One": ["Symphonic", "Metal"], "B - Two": ["Pop"]}


def test_songs_without_a_genre_are_not_stored(tmp_path, fresh_db):
    _song(tmp_path / "A - One", "one.txt", None)
    _song(tmp_path / "B - Two", "two.txt", "Unknown")
    with SessionLocal() as db:
        scan_library(db, root=tmp_path)
    assert _stored() == {}


def test_a_later_scan_follows_a_changed_genre(tmp_path, fresh_db):
    _song(tmp_path / "A - One", "one.txt", "Pop")
    with SessionLocal() as db:
        scan_library(db, root=tmp_path)
    _song(tmp_path / "A - One", "one.txt", "Rock, Pop")
    with SessionLocal() as db:
        scan_library(db, root=tmp_path)
    assert _stored("A - One") == ["Rock", "Pop"]


def test_a_later_scan_forgets_a_removed_genre_and_a_removed_folder(tmp_path, fresh_db):
    _song(tmp_path / "A - One", "one.txt", "Pop")
    _song(tmp_path / "B - Two", "two.txt", "Rock")
    with SessionLocal() as db:
        scan_library(db, root=tmp_path)
    _song(tmp_path / "A - One", "one.txt", "Unknown")
    (tmp_path / "B - Two" / "two.txt").unlink()
    (tmp_path / "B - Two").rmdir()
    _song(tmp_path / "C - Three", "three.txt", "Folk")
    with SessionLocal() as db:
        scan_library(db, root=tmp_path)
    assert _stored() == {"C - Three": ["Folk"]}


def test_a_scan_of_an_unreadable_library_keeps_the_stored_genres(tmp_path, fresh_db):
    _song(tmp_path / "A - One", "one.txt", "Pop")
    with SessionLocal() as db:
        scan_library(db, root=tmp_path)
        scan_library(db, root=tmp_path / "missing")
    assert _stored() == {"A - One": ["Pop"]}



def _factory_folder(root: Path, name: str) -> Path:
    """A song folder as the USDX Song Factory writes it: the song file next to
    its language.txt and lyrics.txt."""
    folder = root / name
    _song(folder, f"{name}.txt", "Folk, Metal")
    (folder / "language.txt").write_text("de\n", encoding="utf-8")
    (folder / "lyrics.txt").write_text("#GENRE:Pop\nWir trinken\n", encoding="utf-8")
    (folder / "readme.TXT").write_text("#NOTE: a header without #BPM\n", encoding="utf-8")
    return folder


def test_only_song_files_count_not_the_other_txt_files(tmp_path):
    folder = _factory_folder(tmp_path, "Equilibrium - Wirtshaus Gaudi")
    assert [p.name for p in song_files(folder)] == ["Equilibrium - Wirtshaus Gaudi.txt"]
    assert folder_genres(folder) == ["Folk", "Metal"]


def test_the_edit_export_names_the_song_file_not_language_txt(fresh_db, tmp_path):
    _factory_folder(tmp_path, "Equilibrium - Wirtshaus Gaudi")
    with SessionLocal() as db:
        db.add(GenreEdit(folder="Equilibrium - Wirtshaus Gaudi", genres="Folk, Metal, Medieval", edited_by="x"))
        db.commit()
        assert genre_edit_lines(db, tmp_path) == \
            "Equilibrium - Wirtshaus Gaudi/Equilibrium - Wirtshaus Gaudi.txt\tFolk, Metal, Medieval\n"



def test_a_factory_helper_file_never_counts_even_with_song_tags(tmp_path):
    folder = tmp_path / "Band - Song"
    _song(folder, "song.txt", "Rock")  # a real song file, whatever its name
    _song(folder, "lyrics.txt", "Pop")
    assert [p.name for p in song_files(folder)] == ["song.txt"]
    assert folder_genres(folder) == ["Rock"]
