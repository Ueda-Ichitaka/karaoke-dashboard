"""Tests for the Genres page (/genres, app/routes/songs.py): the library
explored by the genres the library scan read from the song files
(SongGenre, app/song_genres.py).

Open to every logged-in user (no admin needed); the tab is in everyone's
navigation and a visitor is sent to the login page. The page lists the
genres with their song counts (most songs first), and the songs of the
picked genre - or of every genre when none is picked - as rows with genre
chips, each linking to the song on the Songs page. The search narrows both
by genre, band and title. Only songs in the library with a genre count.
"""

from __future__ import annotations

import re

import pytest

from app.config import settings
from app.database import SessionLocal
from app.models import SongGenre, User
from app.security import hash_password

GENRES = {
    "Queen - Bohemian Rhapsody": ["Rock"],
    "ABBA - Dancing Queen": ["Pop", "Disco"],
    "a-ha - Take On Me": ["Pop"],
    "Toto - Africa": ["Rock", "Pop"],
    "Gone - Not In The Library": ["Metal"],
}


@pytest.fixture()
def genres(fresh_db):
    with SessionLocal() as db:
        for folder, names in GENRES.items():
            for position, name in enumerate(names):
                db.add(SongGenre(folder=folder, genre=name, position=position))
        db.commit()


@pytest.fixture()
def user_client(client, genres):
    with SessionLocal() as db:
        db.add(User(username="singer", password_hash=hash_password("singersinger"), is_admin=False))
        db.commit()
    resp = client.post("/login", data={"username": "singer", "password": "singersinger"},
                       follow_redirects=False)
    assert resp.status_code == 303
    return client


def _genre_list(html: str) -> list[tuple[str, int]]:
    return [(g, int(c)) for g, c in re.findall(r'data-genre="([^"]*)" data-count="(\d+)"', html)]


def _songs(html: str) -> list[str]:
    return re.findall(r'class="genre-song" data-folder="([^"]*)"', html)


def test_the_page_needs_a_login(client):
    r = client.get("/genres", follow_redirects=False)
    assert r.status_code == 303
    assert "/login" in r.headers["location"]


def test_the_tab_is_in_everyones_navigation(client):
    assert 'href="/genres"' in client.get("/songs").text


def test_a_regular_user_sees_the_genres_with_their_song_counts(user_client):
    r = user_client.get("/genres")
    assert r.status_code == 200
    assert _genre_list(r.text) == [("Pop", 3), ("Rock", 2), ("Disco", 1)]


def test_the_head_counts_the_songs_with_a_genre(user_client):
    assert "4 with a genre" in user_client.get("/genres").text


def test_without_a_picked_genre_every_song_with_a_genre_is_listed(user_client):
    songs = _songs(user_client.get("/genres").text)
    assert sorted(songs) == sorted(["Queen - Bohemian Rhapsody", "ABBA - Dancing Queen", "a-ha - Take On Me",
                                    "Toto - Africa"])


def test_a_picked_genre_lists_only_its_songs(user_client):
    r = user_client.get("/genres", params={"genre": "Rock"})
    assert _songs(r.text) == ["Queen - Bohemian Rhapsody", "Toto - Africa"]
    assert "2 songs" in r.text


def test_the_picked_genre_is_marked_in_the_list(user_client):
    r = user_client.get("/genres", params={"genre": "Rock"})
    assert re.search(r'aria-current="true"[^>]*data-genre="Rock"', r.text)


def test_the_picked_genre_names_the_genres_its_songs_share_most(user_client):
    r = user_client.get("/genres", params={"genre": "Pop"})
    assert "Often together with Disco (1), Rock (1)" in r.text


def test_each_song_has_its_genres_as_chips_linking_to_that_genre(user_client):
    r = user_client.get("/genres", params={"genre": "Rock"})
    row = r.text.split('data-folder="Toto - Africa"', 1)[1].split("</li>", 1)[0]
    assert re.findall(r'href="/genres\?genre=([^"&]*)"', row) == ["Rock", "Pop"]


def test_each_song_links_to_it_on_the_songs_page(user_client):
    r = user_client.get("/genres", params={"genre": "Pop"})
    assert 'href="/songs?q=ABBA%20-%20Dancing%20Queen"' in r.text


def test_the_search_narrows_genres_and_songs_by_band_and_title(user_client):
    r = user_client.get("/genres", params={"q": "queen"})
    assert _genre_list(r.text) == [("Disco", 1), ("Pop", 1), ("Rock", 1)]
    assert sorted(_songs(r.text)) == ["ABBA - Dancing Queen", "Queen - Bohemian Rhapsody"]


def test_the_search_finds_songs_by_genre(user_client):
    r = user_client.get("/genres", params={"q": "disco"})
    assert _songs(r.text) == ["ABBA - Dancing Queen"]
    assert _genre_list(r.text) == [("Disco", 1), ("Pop", 1)]


def test_the_search_and_a_picked_genre_combine(user_client):
    r = user_client.get("/genres", params={"q": "queen", "genre": "Pop"})
    assert _songs(r.text) == ["ABBA - Dancing Queen"]


def test_an_unknown_genre_lists_no_songs(user_client):
    r = user_client.get("/genres", params={"genre": "Jazz"})
    assert r.status_code == 200
    assert _songs(r.text) == []
    assert "No songs" in r.text


def test_the_song_list_is_paged_and_the_pager_keeps_genre_and_search(user_client, monkeypatch):
    monkeypatch.setattr(settings, "page_size", 2)
    first = user_client.get("/genres", params={"genre": "Pop"})
    second = user_client.get("/genres", params={"genre": "Pop", "page": 2})
    assert len(_songs(first.text)) == 2
    assert len(_songs(second.text)) == 1
    assert 'href="/genres?genre=Pop&q=&page=2"' in first.text


def test_the_partial_holds_genres_and_songs_without_the_page_chrome(user_client):
    r = user_client.get("/genres/partial", params={"q": "africa"})
    assert r.status_code == 200
    assert "<html" not in r.text.lower()
    assert _songs(r.text) == ["Toto - Africa"]
    assert _genre_list(r.text) == [("Pop", 1), ("Rock", 1)]


def test_the_partial_needs_a_login(client):
    r = client.get("/genres/partial", follow_redirects=False)
    assert r.status_code == 303
