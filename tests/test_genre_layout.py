"""Tests for app/genre_layout.py: the drawings of the Genres page's Map and
Connections tabs, computed on the server as SVG coordinates.

- The biggest `size` genres are shown; a song's place follows its shown
  genres, and a song with none of them goes to "Other genres".
- arrange() (the network) puts genres that share songs close together and
  keeps the others apart; arrange_map() (the map) pulls genres together by
  how many songs they share, at most until they touch, and keeps the others
  MAP_GAP apart - the same input, the same picture.
- Map: one dot per song, inside the circle of its first shown genre (its
  home; "Other genres" when it has none), leaning towards the circles of its
  next three shown genres; no two dots overlap, no two circles overlap and
  no circle drifts far from the others. A circle is sized by its dots and
  labelled with all songs of its genre.
- Connections: one circle per shown genre, a line per pair of genres that
  songs share, one dot per song and pair (a song with three shown genres
  has three dots), a dot around the circle for a song with one genre, and a
  tile per shown genre plus one for "Other genres".
"""

from __future__ import annotations

import math

import pytest

from app.genre_layout import (
    CLUSTER_MIN,
    CLUSTER_SCALE,
    MAP_GAP,
    OTHER_COLOR,
    OTHER_GENRES,
    PALETTE,
    arrange,
    arrange_map,
    genre_map,
    genre_network,
    label_box,
    placement,
    shown_genres,
)
from app.songs import parse_folder


def _library(spec: dict[str, list[str]]):
    songs = [parse_folder(folder) for folder in spec]
    return songs, dict(spec)


def _dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _segment_distance(p, a, b) -> float:
    ax, ay, bx, by, px, py = *a, *b, *p
    length2 = (bx - ax) ** 2 + (by - ay) ** 2
    t = max(0.0, min(1.0, ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / length2))
    return math.hypot(px - (ax + t * (bx - ax)), py - (ay + t * (by - ay)))


LIBRARY = {
    **{f"Pop Band {i} - Song": ["Pop"] for i in range(30)},
    **{f"Metal Band {i} - Song": ["Metal"] for i in range(20)},
    **{f"Heavy Band {i} - Song": ["Heavy", "Metal"] for i in range(10)},
    **{f"Folk Band {i} - Song": ["Folk"] for i in range(5)},
    "Mix - Three": ["Folk", "Heavy", "Metal"],
    "Rare - One": ["Polka"],
    "Rare - Two": ["Jazz", "Polka"],
}


def test_the_biggest_genres_are_shown_most_songs_first():
    songs, genres = _library(LIBRARY)
    assert shown_genres(songs, genres, 3) == ["Metal", "Pop", "Heavy"]


def test_a_song_is_placed_by_its_shown_genres_or_in_other_genres():
    shown = ["Metal", "Pop", "Heavy"]
    assert placement(["Folk", "Heavy", "Metal"], shown) == ["Heavy", "Metal"]
    assert placement(["Jazz", "Polka"], shown) == [OTHER_GENRES]


def test_arrange_is_deterministic():
    sizes = {"A": 40.0, "B": 30.0, "C": 30.0, "D": 20.0}
    shared = {frozenset({"A", "B"}): 10, frozenset({"C", "D"}): 3}
    assert arrange(sizes, shared) == arrange(sizes, shared)


def test_arrange_puts_genres_sharing_songs_close_and_keeps_the_others_apart():
    sizes = {"A": 40.0, "B": 40.0, "C": 40.0, "D": 40.0}
    places = arrange(sizes, {frozenset({"A", "B"}): 10})
    assert _dist(places["A"], places["B"]) < sizes["A"] + sizes["B"]
    for one, other in [("A", "C"), ("A", "D"), ("B", "C"), ("B", "D"), ("C", "D")]:
        assert _dist(places[one], places[other]) >= sizes[one] + sizes[other]


def test_the_map_has_a_cluster_per_shown_genre_and_one_for_other_genres():
    songs, genres = _library(LIBRARY)
    drawing = genre_map(songs, genres, 3, hits=set())
    assert [(c.genre, c.count) for c in drawing.clusters] == [("Metal", 31), ("Pop", 30), ("Heavy", 11),
                                                              (OTHER_GENRES, 7)]
    assert [c.color for c in drawing.clusters] == [*PALETTE[:3], OTHER_COLOR]
    assert drawing.folded == ["Folk", "Polka", "Jazz"]


def test_other_genres_is_left_out_when_every_song_has_a_shown_genre():
    songs, genres = _library({"A - One": ["Pop"], "B - Two": ["Rock"]})
    assert [c.genre for c in genre_map(songs, genres, 2, hits=set()).clusters] == ["Pop", "Rock"]


def test_the_map_has_one_dot_per_song_with_its_genres():
    songs, genres = _library(LIBRARY)
    dots = genre_map(songs, genres, 3, hits=set()).dots
    assert sorted(dot.song.folder for dot in dots) == sorted(LIBRARY)
    assert {dot.song.folder: dot.genres for dot in dots}["Mix - Three"] == ["Folk", "Heavy", "Metal"]


def test_the_search_hits_are_marked():
    songs, genres = _library(LIBRARY)
    dots = genre_map(songs, genres, 3, hits={"Rare - One"}).dots
    assert [dot.song.folder for dot in dots if dot.hit] == ["Rare - One"]


@pytest.mark.parametrize("build", [genre_map, genre_network])
def test_the_view_box_holds_every_circle_and_dot(build):
    songs, genres = _library(LIBRARY)
    drawing = build(songs, genres, 3, hits=set())
    left, top, width, height = (float(v) for v in drawing.view_box.split())
    circles = drawing.clusters if build is genre_map else drawing.nodes
    for c in circles:
        assert left <= c.x - c.r and c.x + c.r <= left + width
        assert top <= c.y - c.r and c.y + c.r <= top + height
    for dot in drawing.dots:
        assert left <= dot.x <= left + width and top <= dot.y <= top + height


def test_the_map_with_more_genres_than_colours_draws_the_rest_grey():
    spec = {f"Band {i} - Song": [f"Genre {i:02d}"] for i in range(len(PALETTE) + 2)}
    songs, genres = _library(spec)
    colors = [c.color for c in genre_map(songs, genres, len(PALETTE) + 2, hits=set()).clusters]
    assert colors == [*PALETTE, OTHER_COLOR, OTHER_COLOR]


def test_the_network_has_a_line_per_shared_pair_with_its_song_count():
    songs, genres = _library(LIBRARY)
    network = genre_network(songs, genres, 3, hits=set())
    assert {(frozenset({e.a, e.b}), e.count) for e in network.edges} == {(frozenset({"Heavy", "Metal"}), 11)}
    assert [(n.genre, n.count) for n in network.nodes] == [("Metal", 31), ("Pop", 30), ("Heavy", 11),
                                                           (OTHER_GENRES, 7)]


def test_the_network_has_a_dot_per_song_and_pair_or_one_around_the_circle():
    songs, genres = _library({"A - One": ["Pop", "Rock", "Metal"], "B - Two": ["Pop"]})
    network = genre_network(songs, genres, 3, hits=set())
    folders = [dot.song.folder for dot in network.dots]
    assert folders.count("A - One") == 3
    assert folders.count("B - Two") == 1
    pop = next(n for n in network.nodes if n.genre == "Pop")
    lone = next(dot for dot in network.dots if dot.song.folder == "B - Two")
    assert _dist((lone.x, lone.y), (pop.x, pop.y)) > pop.r


def test_the_network_dots_of_a_pair_sit_on_its_line():
    songs, genres = _library(LIBRARY)
    network = genre_network(songs, genres, 3, hits=set())
    nodes = {n.genre: n for n in network.nodes}
    metal, heavy = nodes["Metal"], nodes["Heavy"]
    for dot in network.dots:
        if dot.song.folder.startswith("Heavy Band"):
            assert _segment_distance((dot.x, dot.y), (metal.x, metal.y), (heavy.x, heavy.y)) < 12


def test_the_tiles_are_the_shown_genres_and_other_genres_with_their_biggest_bands():
    spec = {**LIBRARY, "Metal Band 0 - Second": ["Metal"], "Metal Band 0 - Third": ["Metal"],
            "Metal Band 1 - Second": ["Metal"]}
    songs, genres = _library(spec)
    tiles = genre_network(songs, genres, 3, hits=set()).tiles
    assert [(t.genre, t.count) for t in tiles] == [("Metal", 34), ("Pop", 30), ("Heavy", 11),
                                                   (OTHER_GENRES, 7)]
    assert tiles[0].bands == ["Metal Band 0", "Metal Band 1", "Heavy Band 0"]
    assert tiles[0].share == 100
    assert tiles[1].share == round(30 * 100 / 34)
    assert tiles[-1].folded == ["Folk", "Polka", "Jazz"]


def test_the_network_circles_never_overlap_even_when_their_genres_share_songs():
    songs, genres = _library(LIBRARY)
    nodes = genre_network(songs, genres, 3, hits=set()).nodes
    for one, other in [(a, b) for i, a in enumerate(nodes) for b in nodes[i + 1:]]:
        assert _dist((one.x, one.y), (other.x, other.y)) >= one.r + other.r


def test_arrange_can_keep_linked_genres_apart_by_a_gap():
    sizes = {"A": 40.0, "B": 40.0}
    places = arrange(sizes, {frozenset({"A", "B"}): 1.0}, overlap=0.0, linked_gap=30.0)
    assert _dist(places["A"], places["B"]) >= 80 + 15


def _overlap(one, other) -> bool:
    return one[0] < other[2] and other[0] < one[2] and one[1] < other[3] and other[1] < one[3]


@pytest.mark.parametrize("build", [genre_map, genre_network])
def test_no_two_genre_labels_overlap(build):
    spec = {
        **{f"Big {i} - Song": ["Metal"] for i in range(80)},
        **{f"Power {i} - Song": ["Power", "Metal"] for i in range(9)},
        **{f"Heavy {i} - Song": ["Heavy", "Metal"] for i in range(8)},
        **{f"Thrash {i} - Song": ["Thrash", "Metal"] for i in range(7)},
    }
    songs, genres = _library(spec)
    drawing = build(songs, genres, 4, hits=set())
    circles = drawing.clusters if build is genre_map else drawing.nodes
    boxes = [label_box(c) for c in circles]
    for i, one in enumerate(boxes):
        for other in boxes[i + 1:]:
            assert not _overlap(one, other)


def test_a_map_label_sits_above_its_cluster():
    songs, genres = _library(LIBRARY)
    for c in genre_map(songs, genres, 3, hits=set()).clusters:
        assert c.label_y <= c.y - c.r - 6


@pytest.mark.parametrize("build", [genre_map, genre_network])
def test_the_drawing_is_wide_like_the_page(build):
    songs, genres = _library(LIBRARY)
    drawing = build(songs, genres, 3, hits=set())
    _, _, width, height = (float(v) for v in drawing.view_box.split())
    assert 1.95 <= width / height <= 2.05
    circles = drawing.clusters if build is genre_map else drawing.nodes
    things = [(c.x, c.y, c.r) for c in circles] + [(d.x, d.y, d.r) for d in drawing.dots]
    used_width = max(x + r for x, _, r in things) - min(x - r for x, _, r in things)
    used_height = max(y + r for _, y, r in things) - min(y - r for _, y, r in things)
    assert used_width / used_height >= 1.6  # spread out wide, not just padded


def test_a_network_label_sits_inside_its_circle():
    songs, genres = _library(LIBRARY)
    for node in genre_network(songs, genres, 3, hits=set()).nodes:
        assert node.y - node.r < node.label_y < node.y + node.r
        assert abs(node.label_y - node.y) <= 6


def _many(count: int, names: list[str]) -> dict[str, list[str]]:
    return {f"{'-'.join(names)} {i} - Song": names for i in range(count)}


def _gap(one, other) -> float:
    return _dist((one.x, one.y), (other.x, other.y)) - one.r - other.r


def _home(dot, shown: list[str]) -> str:
    return placement(dot.genres, shown)[0]


def test_every_dot_sits_inside_the_circle_of_its_first_shown_genre():
    songs, genres = _library(LIBRARY)
    drawing = genre_map(songs, genres, 3, hits=set())
    clusters = {c.genre: c for c in drawing.clusters}
    homes = {dot.song.folder: _home(dot, ["Metal", "Pop", "Heavy"]) for dot in drawing.dots}
    assert homes["Mix - Three"] == "Heavy"  # Folk is folded, Heavy comes before Metal
    assert homes["Rare - Two"] == OTHER_GENRES
    for dot in drawing.dots:
        home = clusters[homes[dot.song.folder]]
        assert _dist((dot.x, dot.y), (home.x, home.y)) + dot.r <= home.r + 0.1


def test_a_circle_is_sized_by_its_dots_and_labelled_with_all_songs_of_its_genre():
    songs, genres = _library(LIBRARY)
    clusters = {c.genre: c for c in genre_map(songs, genres, 3, hits=set()).clusters}
    assert clusters["Metal"].count == 31  # every song with Metal
    assert clusters["Metal"].r == round(CLUSTER_SCALE * math.sqrt(20), 1)  # the 20 whose home it is
    assert clusters["Heavy"].r == round(max(CLUSTER_MIN, CLUSTER_SCALE * math.sqrt(11)), 1)


def test_no_two_map_circles_overlap():
    songs, genres = _library(LIBRARY)
    clusters = genre_map(songs, genres, 3, hits=set()).clusters
    for one, other in [(a, b) for i, a in enumerate(clusters) for b in clusters[i + 1:]]:
        assert _gap(one, other) >= -0.1


def test_no_two_dots_overlap():
    spec = {**LIBRARY, **_many(120, ["Pop", "Heavy"]), **_many(80, ["Metal", "Pop", "Heavy"])}
    songs, genres = _library(spec)
    dots = genre_map(songs, genres, 3, hits=set()).dots
    for i, one in enumerate(dots):
        for other in dots[i + 1:]:
            assert _dist((one.x, one.y), (other.x, other.y)) >= one.r + other.r - 0.1


def _middle(dots) -> tuple[float, float]:
    return sum(d.x for d in dots) / len(dots), sum(d.y for d in dots) / len(dots)


def test_a_dot_leans_towards_the_circles_of_its_next_three_genres():
    spec = {**_many(40, ["Metal"]), **_many(30, ["Pop"]), **_many(30, ["Folk"]), **_many(25, ["Rock"]),
            **_many(20, ["Metal", "Folk"]), **_many(20, ["Metal", "Pop", "Rock"])}
    songs, genres = _library(spec)
    drawing = genre_map(songs, genres, 4, hits=set())
    clusters = {c.genre: c for c in drawing.clusters}
    by_kind = {}
    for dot in drawing.dots:
        by_kind.setdefault(tuple(dot.genres), []).append(dot)
    alone = _middle(by_kind[("Metal",)])
    folk = clusters["Folk"]
    assert _dist(_middle(by_kind[("Metal", "Folk")]), (folk.x, folk.y)) < _dist(alone, (folk.x, folk.y)) - 5
    pop, rock = clusters["Pop"], clusters["Rock"]
    towards = ((pop.x + rock.x) / 2, (pop.y + rock.y) / 2)
    assert _dist(_middle(by_kind[("Metal", "Pop", "Rock")]), towards) < _dist(alone, towards) - 5


def test_the_map_is_the_same_for_the_same_library():
    songs, genres = _library(LIBRARY)
    assert genre_map(songs, genres, 3, hits=set()) == genre_map(songs, genres, 3, hits=set())


def test_arrange_map_brings_genres_closer_the_more_songs_they_share_but_never_overlaps():
    sizes = {"A": 40.0, "B": 40.0, "C": 40.0, "D": 40.0, "E": 40.0}
    links = {frozenset({"A", "B"}): 1.0, frozenset({"C", "D"}): 0.2}
    places = arrange_map(sizes, links)
    assert _dist(places["A"], places["B"]) <= 80 + 1
    assert _dist(places["A"], places["B"]) < _dist(places["C"], places["D"])
    for one, other in [(a, b) for i, a in enumerate(sizes) for b in list(sizes)[i + 1:]]:
        assert _dist(places[one], places[other]) >= sizes[one] + sizes[other] - 0.01
        if frozenset({one, other}) not in links:
            assert _dist(places[one], places[other]) >= sizes[one] + sizes[other] + MAP_GAP - 0.01


def test_no_genre_drifts_far_from_the_others_on_the_map():
    spec = {
        **_many(60, ["Pop"]), **_many(50, ["Metal"]), **_many(35, ["Rock"]), **_many(6, ["Rock", "Metal"]),
        **_many(4, ["Rock", "Pop"]), **_many(8, ["Folk"]), **_many(3, ["Folk", "Rock"]),
        **_many(6, ["Gothic", "Metal"]), **_many(4, ["Gothic"]), **_many(8, ["Classical"]),
        **_many(1, ["Classical", "Pop"]), **_many(5, ["RnB"]), **_many(25, ["Odd"]),
        **{f"Folded {i} - Song": [f"Rare {i}"] for i in range(30)},
    }
    songs, genres = _library(spec)
    clusters = genre_map(songs, genres, 9, hits=set()).clusters
    assert clusters[-1].genre == OTHER_GENRES
    for one in clusters:
        nearest = min(_gap(one, other) for other in clusters if other is not one)
        assert nearest <= MAP_GAP * 1.5, one.genre
