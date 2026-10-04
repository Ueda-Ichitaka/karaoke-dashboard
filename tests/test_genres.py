"""Tests for app/genres.py: the fixed, still-growing genre choice list an
admin can tag a request/report with when reviewing it (several genres at
once - see format_genres/parse_genres for the comma-joined storage on
SongRequest/BrokenReport, app/models.py). "default" means no genre was set.
"""

from __future__ import annotations

from app.genres import (
    DEFAULT_GENRE,
    GENRE_CHOICES,
    format_genres,
    is_valid_genre,
    parse_genres,
)


def test_genre_choices_include_the_requested_list():
    codes = [code for code, _ in GENRE_CHOICES]
    assert codes == [
        "default", "metal", "medieval", "folk", "gothic",
        "symphonic", "punk", "pop", "rap", "kpop", "jpop",
    ]


def test_is_valid_genre():
    assert is_valid_genre("metal")
    assert not is_valid_genre("not-a-genre")


def test_parse_genres_defaults_when_blank():
    assert parse_genres(None) == [DEFAULT_GENRE]
    assert parse_genres("") == [DEFAULT_GENRE]


def test_parse_genres_splits_a_comma_joined_value():
    assert parse_genres("metal,gothic") == ["metal", "gothic"]


def test_format_genres_joins_and_defaults_when_empty():
    assert format_genres(["metal", "gothic"]) == "metal,gothic"
    assert format_genres([]) == DEFAULT_GENRE
