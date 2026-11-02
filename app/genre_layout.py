"""About me: the drawings of the Genres page's Map and Connections tabs
(app/routes/songs.py), computed here as plain SVG coordinates so the
templates only draw them - the same library always gives the same picture.

- The biggest `size` genres are shown (shown_genres; "Genres on the map" on
  the Settings page, DEFAULT_GENRE_MAP_SIZE until saved). A song's place
  is its shown genres; a song with none of them goes to "Other genres"
  (placement), and the genres not shown are listed as folded.
- arrange() places the network's circles: genres that share songs are
  pulled together, the others are pushed apart. arrange_map() places the
  map's: genres are pulled together by how many songs they share (the
  shared part of the smaller genre), at most until they touch, and genres
  that share no songs keep MAP_GAP apart; they start close together and the
  pull to the middle is stronger up and down - as strong as brings the
  circles closest to ASPECT (MAP_PULLS_UP_DOWN) - so they spread out wide
  by themselves, evenly, without one drifting off. Small deterministic
  force layouts - no randomness.
- genre_map(): a circle per genre and one dot per song, inside the circle of
  its first shown genre (its home; "Other genres" when it has none). A
  circle is sized by its dots and labelled with all songs of its genre. A
  dot sits at a scattered spot of its own (from its folder name), leaning
  towards the circles of its song's next three shown genres; then the dots
  are pushed apart until none overlap.
- genre_network(): its own places - circles with the ring of their
  one-genre songs never overlap, linked ones a little apart - with a line per pair of
  genres that songs share (thicker for more songs), a dot per song and pair
  on that line, a dot around the circle for a song with one genre, and a
  tile per genre with its biggest bands.

Both are spread out to about ASPECT (2:1, the shape of the page) and the
view box is padded to exactly that, so a drawing fills the page width. On
the map a genre's label sits above its cluster, moved further up while it
would cover the label of a bigger genre; in the network it sits in the
middle of its circle. Each shown genre has its own colour
from PALETTE, by size; genres past the
palette and "Other genres" are grey (OTHER_COLOR). Search hits (folders)
are marked on the dots.
"""

from __future__ import annotations

import math
import zlib
from collections import Counter
from dataclasses import dataclass, field, replace
from itertools import combinations

from .song_genres import genre_counts
from .songs import Song

DEFAULT_GENRE_MAP_SIZE = 12
MAX_GENRE_MAP_SIZE = 24
OTHER_GENRES = "Other genres"
PALETTE = (
    "#e15759", "#4e79a7", "#f28e2b", "#76b7b2", "#59a14f", "#edc948",
    "#b07aa1", "#ff9da7", "#9c755f", "#17becf", "#bcbd22", "#a0cbe8",
)
OTHER_COLOR = "#7d8592"

CLUSTER_SCALE = 7.2      # map circle radius per square root of its dots
CLUSTER_MIN = 14.0
NODE_BASE, NODE_SCALE = 8.0, 2.6   # network circle radius
MAP_DOT, NET_DOT = 3.0, 2.2        # dot radii
DOT_ROOM = 1.0           # map: space kept between two dots
LEAN = 0.5               # map: how far a dot leans towards its other genres (0..1)
RING_SPACING = 4.5       # spiral step of the songs around a network circle
GAP = 14.0               # network: space kept between genres that share no songs
MAP_GAP = 40.0           # map: space kept between genres that share no songs
NETWORK_LINK_GAP = 40.0  # room for the song dots on a line of the network
MARGIN = 16.0
GOLDEN_ANGLE = math.pi * (3 - math.sqrt(5))
MAP_PULL_SIDEWAYS = 0.995                          # map: pull to the middle per step, sideways
MAP_PULLS_UP_DOWN = (0.985, 0.97, 0.95, 0.93, 0.9)  # and up and down, tried for the closest to ASPECT
MAP_START = 0.3          # map: the circles start on a ring this part of the network's
ASPECT = 2.0             # width : height of a drawing, about that of the page
LABEL_CHAR = 7.6         # width of a label character (13px, bold) - an estimate
LABEL_ABOVE = 8.0        # baseline of a label above its circle
LABEL_STEP = 17.0        # how far a label moves up past another one
LABEL_CENTRE = 4.5       # baseline of a label centred in its circle


@dataclass(frozen=True)
class Circle:
    genre: str
    count: int
    color: str
    x: float
    y: float
    r: float
    label: str = ""         # the text above the circle
    label_y: float = 0.0    # its baseline

    @property
    def is_other(self) -> bool:
        return self.genre == OTHER_GENRES


@dataclass(frozen=True)
class Dot:
    song: Song
    genres: list[str]
    x: float
    y: float
    r: float
    color: str
    hit: bool


@dataclass(frozen=True)
class Edge:
    a: str
    b: str
    count: int
    x1: float
    y1: float
    x2: float
    y2: float
    width: float

    @property
    def pair(self) -> str:
        return "|".join(sorted((self.a, self.b), key=str.casefold))


@dataclass(frozen=True)
class Tile:
    genre: str
    count: int
    color: str
    share: int                      # percent of the biggest tile
    bands: list[str]
    folded: list[str] = field(default_factory=list)

    @property
    def is_other(self) -> bool:
        return self.genre == OTHER_GENRES


@dataclass(frozen=True)
class GenreMap:
    clusters: list[Circle]
    dots: list[Dot]
    view_box: str
    folded: list[str]


@dataclass(frozen=True)
class GenreNetwork:
    nodes: list[Circle]
    edges: list[Edge]
    dots: list[Dot]
    tiles: list[Tile]
    view_box: str
    folded: list[str]


def shown_genres(songs: list[Song], genres: dict[str, list[str]], size: int) -> list[str]:
    """The `size` genres with the most songs, most first, then by name."""
    return [genre for genre, _ in genre_counts(songs, genres)[:size]]


def placement(song_genres: list[str], shown: list[str]) -> list[str]:
    """Where a song goes: its shown genres in file order, or "Other genres"."""
    places = [genre for genre in song_genres if genre in shown]
    return places or [OTHER_GENRES]


def _start(radii: dict[str, float], scale: float) -> dict[str, list[float]]:
    """The circles on a wide ring, in the order of radii."""
    spread = sum(radii.values()) * scale
    return {name: [spread * 0.9 * math.cos(2 * math.pi * i / len(radii)) + 1e-3 * i,
                   spread * 0.45 * math.sin(2 * math.pi * i / len(radii))]
            for i, name in enumerate(radii)}


def _push(pos: dict[str, list[float]], a: str, b: str, amount: float) -> None:
    """Moves a and b along their line, closer for a positive amount."""
    dx, dy = pos[b][0] - pos[a][0], pos[b][1] - pos[a][1]
    d = math.hypot(dx, dy) or 1e-6
    ux, uy = dx / d, dy / d
    pos[a][0] += ux * amount / 2
    pos[a][1] += uy * amount / 2
    pos[b][0] -= ux * amount / 2
    pos[b][1] -= uy * amount / 2


def _distance(pos: dict[str, list[float]], a: str, b: str) -> float:
    return math.hypot(pos[b][0] - pos[a][0], pos[b][1] - pos[a][1])


def arrange(radii: dict[str, float], links: dict[frozenset[str], float], steps: int = 400,
            overlap: float = 0.5, linked_gap: float = 0.0) -> dict[str, tuple[float, float]]:
    """A centre per circle: linked circles are pulled together - to overlap
    by up to `overlap` of their touching distance (link strength 0..1, more
    means closer), plus linked_gap - and never closer than that overlap
    plus half the gap allows; the others are kept at least GAP apart. Deterministic; the order
    of radii decides the start."""
    if not radii:
        return {}
    pos = _start(radii, 1.0)
    pairs = list(combinations(radii, 2))
    for _ in range(steps):
        for a, b in pairs:
            touching = radii[a] + radii[b]
            d = _distance(pos, a, b)
            strength = min(1.0, links.get(frozenset((a, b)), 0.0))
            if strength > 0:
                _push(pos, a, b, (d - touching * (1 - overlap * strength) - linked_gap) * 0.1)
            elif d < touching + GAP:
                _push(pos, a, b, (d - touching - GAP) * 0.5)
        for name in radii:  # a pull to the middle, stronger up and down: a wide picture
            pos[name][0] *= 0.995
            pos[name][1] *= 0.985
    for _ in range(200):  # the last word: no circles closer than allowed
        moved = False
        for a, b in pairs:
            touching = radii[a] + radii[b]
            closest = touching * (1 - overlap) + linked_gap / 2 if frozenset((a, b)) in links else touching
            if _distance(pos, a, b) < closest:
                _push(pos, a, b, _distance(pos, a, b) - closest - GAP / 2)
                moved = True
        if not moved:
            break
    return {name: (pos[name][0], pos[name][1]) for name in radii}


def arrange_map(radii: dict[str, float], links: dict[frozenset[str], float],
                room_above: float = 0.0) -> dict[str, tuple[float, float]]:
    """A centre per map circle (see _arrange_map), with the pull up and down
    that brings the circles closest to ASPECT (room_above: the space a label
    takes above a circle)."""
    if not radii:
        return {}
    tries = [_arrange_map(radii, links, pull) for pull in MAP_PULLS_UP_DOWN]
    return min(tries, key=lambda centres: abs(math.log(_ratio(centres, radii, room_above) / ASPECT)))


def _arrange_map(radii: dict[str, float], links: dict[frozenset[str], float], pull_up_down: float,
                 steps: int = 400) -> dict[str, tuple[float, float]]:
    """A centre per map circle: each pair is kept MAP_GAP apart, less the
    stronger their link (0..1) - touching at the strongest - and pulled
    together up to there by the strength of their link only, so a few shared
    songs barely pull. No two circles overlap. Deterministic; the order of
    radii decides the start."""
    pos = _start(radii, MAP_START)
    pairs = [(a, b, radii[a] + radii[b] + MAP_GAP * (1 - min(1.0, links.get(frozenset((a, b)), 0.0))),
              min(1.0, links.get(frozenset((a, b)), 0.0)))
             for a, b in combinations(radii, 2)]
    for _ in range(steps):
        for a, b, apart, strength in pairs:
            d = _distance(pos, a, b)
            if d < apart:
                _push(pos, a, b, (d - apart) * 0.5)
            elif strength > 0:
                _push(pos, a, b, (d - apart) * 0.1 * strength)
        for name in radii:
            pos[name][0] *= MAP_PULL_SIDEWAYS
            pos[name][1] *= pull_up_down
    for _ in range(200):  # the last word: no circles closer than allowed
        moved = False
        for a, b, apart, _ in pairs:
            if _distance(pos, a, b) < apart - 1e-6:
                _push(pos, a, b, _distance(pos, a, b) - apart)
                moved = True
        if not moved:
            break
    return {name: (pos[name][0], pos[name][1]) for name in radii}


def _ratio(centres, radii: dict[str, float], room_above: float) -> float:
    """Width : height of the circles (room_above: the space a label takes above a circle)."""
    width = max(x + radii[n] for n, (x, _) in centres.items()) - min(x - radii[n] for n, (x, _) in centres.items())
    height = (max(y + radii[n] for n, (_, y) in centres.items())
              - min(y - radii[n] - room_above for n, (_, y) in centres.items()))
    return width / height


def widen(centres: dict[str, tuple[float, float]], radii: dict[str, float],
          room_above: float = 0.0) -> dict[str, tuple[float, float]]:
    """The centres spread apart along one axis - circles only ever move
    further apart - until the circles take up about ASPECT times as much
    width as height (room_above: the space a label takes above a circle)."""
    pos = {name: list(xy) for name, xy in centres.items()}
    if len(pos) < 2:
        return centres
    for _ in range(40):
        ratio = _ratio(pos, radii, room_above)
        if abs(ratio - ASPECT) <= ASPECT * 0.01:
            break
        axis, factor = (0, min(1.25, ASPECT / ratio)) if ratio < ASPECT else (1, min(1.25, ratio / ASPECT))
        middle = sum(xy[axis] for xy in pos.values()) / len(pos)
        for xy in pos.values():
            xy[axis] = middle + (xy[axis] - middle) * factor
    return {name: (xy[0], xy[1]) for name, xy in pos.items()}


def label_box(circle: Circle) -> tuple[float, float, float, float]:
    """The space a circle's label takes: left, top, right, bottom."""
    half = len(circle.label) * LABEL_CHAR / 2
    return circle.x - half, circle.label_y - 14, circle.x + half, circle.label_y + 4


def _place_labels(circles: list[Circle]) -> list[Circle]:
    """Each label just above its circle - moved further up while it would
    cover a label of a bigger circle."""
    placed: dict[str, Circle] = {}
    for circle in sorted(circles, key=lambda c: -c.r):
        moved = replace(circle, label_y=round(circle.y - circle.r - LABEL_ABOVE, 1))
        for _ in range(len(circles) * 3):
            box = label_box(moved)
            if not any(box[0] < other[2] and other[0] < box[2] and box[1] < other[3] and other[1] < box[3]
                       for other in map(label_box, placed.values())):
                break
            moved = replace(moved, label_y=round(moved.label_y - LABEL_STEP, 1))
        placed[circle.genre] = moved
    return [placed[circle.genre] for circle in circles]


def _color(index: int) -> str:
    return PALETTE[index] if index < len(PALETTE) else OTHER_COLOR


def _view_box(circles: list[Circle], dots: list[Dot]) -> str:
    if not circles:
        return "0 0 100 100"
    left = min([min(c.x - c.r, label_box(c)[0]) for c in circles] + [d.x - d.r for d in dots])
    right = max([max(c.x + c.r, label_box(c)[2]) for c in circles] + [d.x + d.r for d in dots])
    top = min([min(c.y - c.r, label_box(c)[1]) for c in circles] + [d.y - d.r for d in dots])
    bottom = max([c.y + c.r for c in circles] + [d.y + d.r for d in dots])
    left, top, right, bottom = left - MARGIN, top - MARGIN, right + MARGIN, bottom + MARGIN
    width, height = right - left, bottom - top
    if width < height * ASPECT:  # the rest as even space on both sides, for the exact ASPECT
        left -= (height * ASPECT - width) / 2
        width = height * ASPECT
    else:
        top -= (width / ASPECT - height) / 2
        height = width / ASPECT
    return f"{left:.1f} {top:.1f} {width:.1f} {height:.1f}"


@dataclass(frozen=True)
class _Groups:
    order: list[str]                         # shown genres, then "Other genres" when used
    places: list[tuple[Song, list[str]]]     # each song with a genre and its place
    counts: Counter
    shared: Counter                          # frozenset pair -> songs
    folded: list[str]
    links: dict[frozenset[str], float]      # pair -> shared part of the smaller genre


def _groups(songs: list[Song], genres: dict[str, list[str]], size: int) -> _Groups:
    library = [song for song in songs if genres.get(song.folder)]
    shown = shown_genres(library, genres, size)
    places = [(song, placement(genres[song.folder], shown)) for song in library]
    counts = Counter(genre for _, place in places for genre in place)
    shared = Counter(frozenset(pair) for _, place in places for pair in combinations(place, 2))
    order = shown + ([OTHER_GENRES] if counts[OTHER_GENRES] else [])
    links = {pair: n / min(counts[g] for g in pair) for pair, n in shared.items()}
    folded = [genre for genre, _ in genre_counts(library, genres) if genre not in shown]
    return _Groups(order, places, counts, shared, folded, links)


def _circles(groups: _Groups, centres: dict[str, tuple[float, float]], radii: dict[str, float],
             label) -> list[Circle]:
    """A circle per genre, counting all songs of its genre."""
    return [
        Circle(genre, groups.counts[genre], OTHER_COLOR if genre == OTHER_GENRES else _color(i),
               round(centres[genre][0], 1), round(centres[genre][1], 1), round(radii[genre], 1),
               label(genre, groups.counts[genre]))
        for i, genre in enumerate(groups.order)
    ]


def _cluster_radius(songs: int) -> float:
    return max(CLUSTER_MIN, CLUSTER_SCALE * math.sqrt(songs))


def _node_radius(songs: int) -> float:
    return NODE_BASE + NODE_SCALE * math.sqrt(songs)


def _scatter(folder: str) -> tuple[float, float]:
    """A song's own spot in a circle of radius 1, the same for the same
    folder name and spread evenly over the area."""
    h = zlib.crc32(folder.encode())
    angle = 2 * math.pi * (h & 0xFFFF) / 0x10000
    reach = math.sqrt(((h >> 16) + 0.5) / 0x10000)
    return reach * math.cos(angle), reach * math.sin(angle)


def _lean(home: Circle, others: list[Circle]) -> tuple[float, float]:
    """The way from a circle's middle towards the other circles, each
    counting the same - length 1, or nothing without others."""
    x = y = 0.0
    for other in others:
        d = math.hypot(other.x - home.x, other.y - home.y) or 1e-6
        x, y = x + (other.x - home.x) / d, y + (other.y - home.y) / d
    length = math.hypot(x, y)
    return (x / length, y / length) if length > 1e-9 else (0.0, 0.0)


def _settle(points: list[list[float]], room: float, steps: int = 80) -> None:
    """Pushes the points (relative to a circle's middle) apart until no two
    are closer than two dots and DOT_ROOM, keeping each within `room` of
    the middle."""
    apart = 2 * MAP_DOT + DOT_ROOM
    for _ in range(steps):
        cells: dict[tuple[int, int], list[int]] = {}
        for i, (x, y) in enumerate(points):
            cells.setdefault((math.floor(x / apart), math.floor(y / apart)), []).append(i)
        moved = False
        for (cx, cy), members in cells.items():
            near = [j for dx in (-1, 0, 1) for dy in (-1, 0, 1) for j in cells.get((cx + dx, cy + dy), ())]
            for i in members:
                for j in near:
                    if j <= i:
                        continue
                    dx, dy = points[j][0] - points[i][0], points[j][1] - points[i][1]
                    d = math.hypot(dx, dy)
                    if d < apart:
                        if d < 1e-9:
                            dx, dy, d = math.cos(i), math.sin(i), 1.0
                        shift = (apart - d) / 2 + 1e-3
                        points[i][0] -= dx / d * shift
                        points[i][1] -= dy / d * shift
                        points[j][0] += dx / d * shift
                        points[j][1] += dy / d * shift
                        moved = True
        for point in points:
            d = math.hypot(point[0], point[1])
            if d > room:
                point[0], point[1] = point[0] * room / d, point[1] * room / d
        if not moved:
            return


def genre_map(songs: list[Song], genres: dict[str, list[str]], size: int, hits: set[str]) -> GenreMap:
    """The Map tab: a circle per genre and one dot per song with a genre, in
    the circle of its first shown genre and leaning towards its next three."""
    groups = _groups(songs, genres, size)
    homes = Counter(place[0] for _, place in groups.places)
    radii = {genre: _cluster_radius(homes[genre]) for genre in groups.order}
    centres = widen(arrange_map(radii, groups.links, room_above=LABEL_ABOVE + 14), radii,
                    room_above=LABEL_ABOVE + 14)
    clusters = _place_labels(_circles(groups, centres, radii, lambda genre, count: f"{genre} {count}"))
    by_genre = {c.genre: c for c in clusters}
    members: dict[str, list[tuple[Song, list[str]]]] = {}
    for song, place in sorted(groups.places, key=lambda item: item[0].folder):
        members.setdefault(place[0], []).append((song, place))
    dots = []
    for genre in groups.order:
        home = by_genre[genre]
        room = home.r - MAP_DOT
        points = []
        for song, place in members.get(genre, []):
            sx, sy = _scatter(song.folder)
            lx, ly = _lean(home, [by_genre[other] for other in place[1:4]])
            points.append([room * (sx * (1 - LEAN) + lx * LEAN) if lx or ly else room * sx,
                           room * (sy * (1 - LEAN) + ly * LEAN) if lx or ly else room * sy])
        _settle(points, room)
        for (song, _), (x, y) in zip(members.get(genre, []), points, strict=True):
            dots.append(Dot(song, genres[song.folder], round(home.x + x, 1), round(home.y + y, 1), MAP_DOT,
                            home.color, song.folder in hits))
    return GenreMap(clusters, dots, _view_box(clusters, dots), groups.folded)


def _top_bands(songs: list[Song], limit: int = 3) -> list[str]:
    counts = Counter(song.artist for song in songs if song.artist)
    return [band for band, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0].casefold()))[:limit]]


def genre_network(songs: list[Song], genres: dict[str, list[str]], size: int, hits: set[str]) -> GenreNetwork:
    """The Connections tab: a circle per genre, lines for the genres songs
    share with their songs as dots, and a tile per genre."""
    groups = _groups(songs, genres, size)
    singles = Counter(place[0] for _, place in groups.places if len(place) == 1)
    reach = {genre: _node_radius(groups.counts[genre]) + 7 + RING_SPACING * math.sqrt(singles[genre] + 0.5)
             for genre in groups.order}  # a circle with the ring of its one-genre songs
    centres = widen(arrange(reach, groups.links, overlap=0.0, linked_gap=NETWORK_LINK_GAP), reach)
    radii = {genre: _node_radius(groups.counts[genre]) for genre in groups.order}
    nodes = [replace(node, label_y=round(node.y + LABEL_CENTRE, 1))
             for node in _circles(groups, centres, radii, lambda genre, count: genre)]
    by_genre = {n.genre: n for n in nodes}
    top = max(groups.shared.values(), default=1)
    edges = []
    dots = []
    for pair, count in sorted(groups.shared.items(), key=lambda item: (-item[1], sorted(item[0]))):
        a, b = sorted(pair, key=groups.order.index)
        na, nb = by_genre[a], by_genre[b]
        edges.append(Edge(a, b, count, na.x, na.y, nb.x, nb.y, round(1 + 4 * math.sqrt(count / top), 1)))
        length = math.hypot(nb.x - na.x, nb.y - na.y) or 1e-6
        start, end = (na.r + 6) / length, 1 - (nb.r + 6) / length
        if start >= end:
            start = end = 0.5
        nx, ny = -(nb.y - na.y) / length, (nb.x - na.x) / length
        on_line = [(song, place) for song, place in groups.places if a in place and b in place]
        for k, (song, _) in enumerate(on_line):
            t = start + (end - start) * (k + 0.5) / len(on_line)
            offset = ((k % 3) - 1) * 4.0
            dots.append(Dot(song, genres[song.folder], round(na.x + (nb.x - na.x) * t + nx * offset, 1),
                            round(na.y + (nb.y - na.y) * t + ny * offset, 1), NET_DOT, OTHER_COLOR,
                            song.folder in hits))
    rings: dict[str, int] = {}
    for song, place in groups.places:
        if len(place) != 1:
            continue
        node = by_genre[place[0]]
        k = rings.get(node.genre, 0)
        rings[node.genre] = k + 1
        rho = node.r + 5 + RING_SPACING * math.sqrt(k + 0.5)
        dots.append(Dot(song, genres[song.folder], round(node.x + rho * math.cos(k * GOLDEN_ANGLE), 1),
                        round(node.y + rho * math.sin(k * GOLDEN_ANGLE), 1), NET_DOT, node.color,
                        song.folder in hits))
    biggest = max((n.count for n in nodes), default=1)
    tiles = [
        Tile(n.genre, n.count, n.color, round(n.count * 100 / biggest),
             _top_bands([song for song, place in groups.places if n.genre in place]),
             groups.folded if n.is_other else [])
        for n in nodes
    ]
    return GenreNetwork(nodes, edges, dots, tiles, _view_box(nodes, dots), groups.folded)
