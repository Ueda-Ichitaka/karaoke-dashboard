"""Tests for editing a song's genres on the Genres page's Edit tab
(/genres/edit, app/routes/songs.py; GenreEdit, app/song_genres.py).

- Only contributors and admins see and use the tab. It lists every song -
  also those without a genre - paged and searchable, optionally only the
  songs with an open edit.
- Saving stores an edit (the text split like a #GENRE value; empty or only
  placeholders is refused). Saving the file's own genres, or Reset, drops
  it. A fetch from app/static/app.js gets JSON, a plain form a redirect.
- The rest of the Genres page uses the edited genres at once. A library
  scan that reads the same genres from the song files ends the edit.
- The export lists every open edit as tab-separated lines: the path of each
  song file of the folder (relative to the library root) and the genres.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import select

from app.database import SessionLocal
from app.models import GenreEdit, SongGenre, User
from app.security import hash_password
from app.song_genres import record_genres
from app.songs import all_songs, total_count
from tests.conftest import SONGS_DIR

FILE_GENRES = {
    "Testband - Solo Song": ["Rock"],
    "Queen - Bohemian Rhapsody": ["Rock", "Opera"],
}
FETCH = {"X-Requested-With": "fetch"}


def _login(client, username: str, **flags):
    with SessionLocal() as db:
        for folder, names in FILE_GENRES.items():
            for position, name in enumerate(names):
                db.add(SongGenre(folder=folder, genre=name, position=position))
        db.add(User(username=username, password_hash=hash_password("secretsecret"), **flags))
        db.commit()
    r = client.post("/login", data={"username": username, "password": "secretsecret"}, follow_redirects=False)
    assert r.status_code == 303
    return client


@pytest.fixture()
def contributor(client):
    return _login(client, "helper", is_contributor=True)


@pytest.fixture()
def singer(client):
    return _login(client, "singer")


def _edits() -> dict[str, str]:
    with SessionLocal() as db:
        return {e.folder: e.genres for e in db.scalars(select(GenreEdit))}


def _save(client, folder: str, genres: str, **kwargs):
    return client.post("/genres/edit", data={"folder": folder, "genres": genres}, follow_redirects=False, **kwargs)


def _rows(html: str) -> dict[str, str]:
    """Each listed song's folder with the value of its genre field."""
    return dict(re.findall(r'<li class="genre-edit-row[^"]*" data-folder="([^"]*)".*?name="genres" value="([^"]*)"',
                           html, re.S))


# --------------------------------------------------------------------------- who may

def test_the_edit_tab_needs_a_login(client):
    r = client.get("/genres/edit", follow_redirects=False)
    assert r.status_code == 303 and "/login" in r.headers["location"]


@pytest.mark.parametrize(("method", "url"), [("get", "/genres/edit"), ("get", "/genres/edit/export.tsv"),
                                             ("post", "/genres/edit"), ("post", "/genres/edit/reset")])
def test_a_plain_user_may_not_edit(singer, method, url):
    r = getattr(singer, method)(url, **({"data": {"folder": "Testband - Solo Song", "genres": "Pop"}}
                                        if method == "post" else {}))
    assert r.status_code == 403


def test_a_contributor_sees_the_edit_tab_in_the_tab_row(contributor):
    row = contributor.get("/genres").text.split('class="genre-tabs"', 1)[1].split("</nav>", 1)[0]
    assert re.findall(r'<a href="([^"?]*)', row) == ["/genres", "/genres/map", "/genres/connections", "/genres/edit"]


def test_a_plain_user_sees_no_edit_tab(singer):
    assert "/genres/edit" not in singer.get("/genres").text


# --------------------------------------------------------------------------- the list

def test_the_edit_tab_lists_every_song_with_its_genres(contributor):
    rows = _rows(contributor.get("/genres/edit").text)
    assert len(rows) == total_count()
    assert rows["Testband - Solo Song"] == "Rock"
    assert rows["Queen - Bohemian Rhapsody"] == "Rock, Opera"
    assert rows["Toto - Africa"] == ""


def test_the_edit_tab_searches_also_the_songs_without_a_genre(contributor):
    rows = _rows(contributor.get("/genres/edit", params={"q": "toto"}).text)
    assert list(rows) == ["Toto - Africa"]
    assert list(_rows(contributor.get("/genres/edit", params={"q": "opera"}).text)) == ["Queen - Bohemian Rhapsody"]


def test_the_edit_tab_can_show_only_the_edited_songs(contributor):
    _save(contributor, "Toto - Africa", "Pop")
    assert list(_rows(contributor.get("/genres/edit", params={"edited": "1"}).text)) == ["Toto - Africa"]


def test_the_edit_tab_suggests_the_known_genres(contributor):
    _save(contributor, "Toto - Africa", "Soft Rock")
    html = contributor.get("/genres/edit").text
    datalist = html.split('<datalist id="genre-suggestions">', 1)[1].split("</datalist>", 1)[0]
    assert re.findall(r'<option value="([^"]*)">', datalist) == ["Opera", "Rock", "Soft Rock"]


def test_an_edited_row_shows_the_file_genres_and_a_reset(contributor):
    _save(contributor, "Queen - Bohemian Rhapsody", "Opera, Rock")
    html = contributor.get("/genres/edit").text
    row = re.search(r'<li class="genre-edit-row edited" data-folder="Queen - Bohemian Rhapsody".*?</li>', html,
                    re.S).group(0)
    assert "In the song file: Rock, Opera" in " ".join(re.sub(r"<[^>]+>", "", row).split())
    assert re.search(r'<form class="genre-reset"[^>]*>', row).group(0).count("hidden") == 0
    plain = re.search(r'<li class="genre-edit-row" data-folder="Toto - Africa".*?</li>', html, re.S).group(0)
    assert re.search(r'<form class="genre-reset"[^>]*hidden', plain)


# --------------------------------------------------------------------------- saving

def test_saving_stores_the_genres_split_like_a_genre_tag(contributor):
    r = _save(contributor, "Toto - Africa", " Soft Rock ,pop, unknown, Pop,  Heavy\tMetal ")
    assert r.status_code == 303
    assert _edits() == {"Toto - Africa": "Soft Rock, pop, Heavy Metal"}
    with SessionLocal() as db:
        edit = db.scalar(select(GenreEdit))
        assert edit.edited_by == "helper" and edit.edited_at is not None


def test_a_plain_form_goes_back_to_the_same_search_and_page(contributor):
    r = contributor.post("/genres/edit", data={"folder": "Toto - Africa", "genres": "Pop", "q": "to to",
                                               "page": "2", "edited": "1"}, follow_redirects=False)
    assert r.headers["location"] == "/genres/edit?q=to%20to&page=2&edited=1#Toto%20-%20Africa"


def test_a_fetch_gets_the_saved_row_as_json(contributor):
    r = _save(contributor, "Queen - Bohemian Rhapsody", "Opera", headers=FETCH)
    assert r.status_code == 200
    assert r.json() == {"genres": "Opera", "edited": True, "file_genres": "Rock, Opera"}


@pytest.mark.parametrize("genres", ["", "  ,  ", "unknown, misc"])
def test_saving_no_genre_is_refused(contributor, genres):
    r = _save(contributor, "Toto - Africa", genres, headers=FETCH)
    assert r.status_code == 422
    assert r.json() == {"error": "Enter at least one genre."}
    r = _save(contributor, "Toto - Africa", genres)
    assert r.status_code == 303
    assert "error=Enter%20at%20least%20one%20genre." in r.headers["location"]
    assert _edits() == {}
    assert "Enter at least one genre." in contributor.get(r.headers["location"]).text


def test_saving_the_file_genres_drops_the_edit(contributor):
    _save(contributor, "Queen - Bohemian Rhapsody", "Opera")
    r = _save(contributor, "Queen - Bohemian Rhapsody", "rock, opera", headers=FETCH)
    assert r.json() == {"genres": "Rock, Opera", "edited": False, "file_genres": "Rock, Opera"}
    assert _edits() == {}


def test_reset_drops_the_edit(contributor):
    _save(contributor, "Queen - Bohemian Rhapsody", "Opera")
    r = contributor.post("/genres/edit/reset", data={"folder": "Queen - Bohemian Rhapsody"}, headers=FETCH)
    assert r.json() == {"genres": "Rock, Opera", "edited": False, "file_genres": "Rock, Opera"}
    assert _edits() == {}


def test_editing_an_unknown_song_is_refused(contributor):
    assert _save(contributor, "Nobody - Nothing", "Pop").status_code == 404


# --------------------------------------------------------------------------- everywhere else

def test_the_genres_page_uses_the_edited_genres(contributor):
    _save(contributor, "Toto - Africa", "Soft Rock")
    _save(contributor, "Queen - Bohemian Rhapsody", "Opera")
    html = contributor.get("/genres").text
    assert re.findall(r'data-genre="([^"]*)" data-count="(\d+)"', html) == \
        [("Opera", "1"), ("Rock", "1"), ("Soft Rock", "1")]
    dots = re.findall(r'class="map-dot[^"]*"[^>]*data-folder="([^"]*)"[^>]*data-genres="([^"]*)"',
                      contributor.get("/genres/map").text)
    assert sorted(dots) == [("Queen - Bohemian Rhapsody", "Opera"), ("Testband - Solo Song", "Rock"),
                            ("Toto - Africa", "Soft Rock")]


def test_a_scan_that_reads_the_edited_genres_ends_the_edit(fresh_db):
    folders = [song.folder for song in all_songs()]
    with SessionLocal() as db:
        db.add(GenreEdit(folder="Testband - Solo Song", genres="ROCK", edited_by="helper"))
        db.add(GenreEdit(folder="Coverband - Copycat Song", genres="Pop", edited_by="helper"))
        db.commit()
        record_genres(db, SONGS_DIR, folders)
        db.commit()
    assert _edits() == {"Coverband - Copycat Song": "Pop"}


# --------------------------------------------------------------------------- export

def test_the_export_lists_each_song_file_of_every_open_edit(contributor):
    _save(contributor, "Testband - Multi Song", "Pop, Rock")
    _save(contributor, "Testband - Solo Song", "Hard Rock")
    r = contributor.get("/genres/edit/export.tsv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/tab-separated-values")
    assert r.headers["content-disposition"] == 'attachment; filename="genre-edits.tsv"'
    assert r.text == ("Testband - Multi Song/SongA.txt\tPop, Rock\n"
                      "Testband - Multi Song/SongB.txt\tPop, Rock\n"
                      "Testband - Solo Song/Solo Song.txt\tHard Rock\n")


def test_the_edit_tab_links_the_export_with_the_number_of_open_edits(contributor):
    _save(contributor, "Toto - Africa", "Pop")
    html = contributor.get("/genres/edit").text
    assert re.search(r'<a [^>]*href="/genres/edit/export.tsv"[^>]*>Export 1 edit</a>', html)
