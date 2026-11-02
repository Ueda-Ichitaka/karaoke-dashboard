"""Tests for the Genres page's tabs (app/routes/songs.py): List (/genres),
Map (/genres/map) and Connections (/genres/connections), drawn as SVG on
the server (app/genre_layout.py).

Every tab needs a login and shares the head: the search and the tab row,
whose links keep the search. The Map has a cluster per shown genre (as
many as "Genres on the map" on the Settings page) linking to that genre on
the List tab, and one dot per song with its band, title and genres, linking
to the song on the Songs page; a search marks the matching dots. The
Connections tab has a tile per shown genre and a line per pair of genres
that songs share.
"""

from __future__ import annotations

import re

import pytest

from app.app_settings import get_app_settings
from app.database import SessionLocal
from app.models import SongGenre, User
from app.security import hash_password
from app.songs import total_count

GENRES = {
    "Queen - Bohemian Rhapsody": ["Rock"],
    "ABBA - Dancing Queen": ["Pop", "Disco"],
    "a-ha - Take On Me": ["Pop"],
    "Toto - Africa": ["Rock", "Pop"],
}
TABS = [("List", "/genres"), ("Map", "/genres/map"), ("Connections", "/genres/connections")]


@pytest.fixture()
def user_client(client):
    with SessionLocal() as db:
        for folder, names in GENRES.items():
            for position, name in enumerate(names):
                db.add(SongGenre(folder=folder, genre=name, position=position))
        db.add(User(username="singer", password_hash=hash_password("singersinger"), is_admin=False))
        db.commit()
    resp = client.post("/login", data={"username": "singer", "password": "singersinger"},
                       follow_redirects=False)
    assert resp.status_code == 303
    return client


def _tab_row(html: str) -> str:
    return html.split('class="genre-tabs"', 1)[1].split("</nav>", 1)[0]


def _dots(html: str) -> list[str]:
    return re.findall(r'class="map-dot[^"]*"[^>]*data-folder="([^"]*)"', html)


def _hits(html: str) -> list[str]:
    return re.findall(r'class="map-dot hit"[^>]*data-folder="([^"]*)"', html)


@pytest.mark.parametrize("url", ["/genres/map", "/genres/connections"])
def test_the_tabs_need_a_login(client, url):
    r = client.get(url, follow_redirects=False)
    assert r.status_code == 303
    assert "/login" in r.headers["location"]


@pytest.mark.parametrize(("active", "url"), TABS)
def test_every_tab_has_the_tab_row_with_itself_current(user_client, active, url):
    row = _tab_row(user_client.get(url).text)
    assert re.findall(r'<a href="([^"]*)"', row) == [u for _, u in TABS]
    assert re.findall(r'aria-current="page"[^>]*>([^<]*)<', row) == [active]


@pytest.mark.parametrize(("active", "url"), TABS)
def test_the_tab_links_keep_the_search(user_client, active, url):
    row = _tab_row(user_client.get(url, params={"q": "a b"}).text)
    assert re.findall(r'<a href="([^"]*)"', row) == [f"{u}?q=a%20b" for _, u in TABS]


@pytest.mark.parametrize(("active", "url"), TABS)
def test_every_tab_searches_on_itself(user_client, active, url):
    assert f'<form class="search" method="get" action="{url}"' in user_client.get(url).text


def test_the_map_has_a_dot_per_song_with_a_genre(user_client):
    assert sorted(_dots(user_client.get("/genres/map").text)) == sorted(GENRES)


def test_a_map_dot_names_its_song_and_links_to_it(user_client):
    html = user_client.get("/genres/map").text
    dot = re.search(r'<a class="map-dot[^"]*"[^>]*data-folder="Toto - Africa".*?</a>', html, re.S).group(0)
    assert 'href="/songs?q=Toto%20-%20Africa"' in dot
    assert 'data-artist="Toto"' in dot and 'data-title="Africa"' in dot
    assert 'data-genres="Rock|Pop"' in dot
    assert "<title>Toto - Africa (Rock, Pop)</title>" in dot


def test_the_map_clusters_link_to_their_genre_on_the_list_tab(user_client):
    html = user_client.get("/genres/map").text
    assert re.findall(r'<a class="map-cluster" href="/genres\?genre=([^"]*)"', html) == ["Pop", "Rock", "Disco"]


def test_the_map_marks_the_search_hits(user_client):
    html = user_client.get("/genres/map", params={"q": "queen"}).text
    assert sorted(_hits(html)) == ["ABBA - Dancing Queen", "Queen - Bohemian Rhapsody"]
    assert "2 songs match" in html
    assert _hits(user_client.get("/genres/map").text) == []


def test_the_map_shows_as_many_genres_as_the_setting_says(user_client):
    with SessionLocal() as db:
        get_app_settings(db).genre_map_size = 1
        db.commit()
    html = user_client.get("/genres/map").text
    assert re.findall(r'class="map-cluster"[^>]*data-genre="([^"]*)"', html) == ["Pop", "Other genres"]
    assert "Other genres: Rock, Disco" in html


def test_the_map_counts_the_songs_left_out(user_client):
    assert f"Not on the map: {total_count() - len(GENRES)} songs without a genre" in \
        user_client.get("/genres/map").text


def test_the_map_has_the_song_card_for_a_clicked_dot(user_client):
    assert "data-song-card hidden" in user_client.get("/genres/map").text


def test_the_connections_tab_has_a_tile_per_shown_genre(user_client):
    html = user_client.get("/genres/connections").text
    assert re.findall(r'class="genre-tile" href="/genres\?genre=([^"]*)" data-count="(\d+)"', html) == \
        [("Pop", "3"), ("Rock", "2"), ("Disco", "1")]


def test_the_connections_tab_has_a_line_per_shared_pair(user_client):
    html = user_client.get("/genres/connections").text
    assert sorted(re.findall(r'class="net-edge" data-pair="([^"]*)" data-count="(\d+)"', html)) == \
        [("Disco|Pop", "1"), ("Pop|Rock", "1")]


def test_the_connections_tab_marks_the_search_hits(user_client):
    html = user_client.get("/genres/connections", params={"q": "africa"}).text
    assert set(re.findall(r'class="map-dot hit"[^>]*data-folder="([^"]*)"', html)) == {"Toto - Africa"}


def test_the_other_genres_tile_names_at_most_eight_folded_genres(user_client):
    with SessionLocal() as db:
        for i in range(12):
            db.add(SongGenre(folder="Queen - Bohemian Rhapsody", genre=f"Rare {i:02d}", position=i + 1))
        get_app_settings(db).genre_map_size = 1
        db.commit()
    html = user_client.get("/genres/connections").text
    tile = html.split("genre-tile-other", 1)[1].split("</div>", 1)[0]
    assert "Rock, Disco, Rare 00, Rare 01, Rare 02, Rare 03, Rare 04, Rare 05 and 6 more" in tile
