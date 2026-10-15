"""Tests for app/import_merge.py: the merge rules the report and request CSV
imports share when a row lands on a song that already has a report or
request.
"""

from __future__ import annotations

from app import import_merge

GENIUS_A = "https://genius.com/a-lyrics"
GENIUS_B = "https://genius.com/b-lyrics"
LRCLIB_A = "https://lrclib.net/tracks/1"
LRCLIB_B = "https://lrclib.net/tracks/2"


def test_lyrics_link_fills_in_when_missing():
    assert import_merge.preferred_lyrics_link(None, GENIUS_A) == GENIUS_A
    assert import_merge.preferred_lyrics_link(GENIUS_A, "") == GENIUS_A


def test_lrclib_link_wins_over_any_other_link():
    assert import_merge.preferred_lyrics_link(GENIUS_A, LRCLIB_A) == LRCLIB_A
    assert import_merge.preferred_lyrics_link(LRCLIB_A, GENIUS_A) == LRCLIB_A
    assert import_merge.preferred_lyrics_link(GENIUS_A, "https://www.LRCLIB.net/tracks/9") == (
        "https://www.LRCLIB.net/tracks/9"
    )


def test_same_kind_lyrics_links_keep_the_existing_one():
    assert import_merge.preferred_lyrics_link(GENIUS_A, GENIUS_B) == GENIUS_A
    assert import_merge.preferred_lyrics_link(LRCLIB_A, LRCLIB_B) == LRCLIB_A


def test_codes_are_combined_and_the_default_only_stands_alone():
    assert import_merge.merge_codes("metal", ["gothic"], "default") == "metal,gothic"
    assert import_merge.merge_codes("default", ["gothic"], "default") == "gothic"
    assert import_merge.merge_codes("metal", ["default"], "default") == "metal"
    assert import_merge.merge_codes("metal,gothic", ["gothic"], "default") == "metal,gothic"
    assert import_merge.merge_codes(None, [], "none") == "none"


def test_text_already_contained_is_not_appended_again():
    assert import_merge.append_new_text("cuts out; needs re-timing", "Needs Re-Timing") == "cuts out; needs re-timing"
    assert import_merge.append_new_text("cuts out", "wrong key") == "cuts out; wrong key"
    assert import_merge.append_new_text("", "wrong key") == "wrong key"
    assert import_merge.append_new_text("cuts out", "") == "cuts out"


def test_conflicting_value_keeps_the_existing_one_and_notes_it():
    notes: list[str] = []
    assert import_merge.keep_or_fill("de", "en", "language", notes) == "de"
    assert notes == ['language differs: kept "de", file has "en"']


def test_missing_value_is_filled_in_and_equal_values_need_no_note():
    notes: list[str] = []
    assert import_merge.keep_or_fill(None, "en", "language", notes) == "en"
    assert import_merge.keep_or_fill("en", "en", "language", notes) == "en"
    assert import_merge.keep_or_fill("en", "", "language", notes) == "en"
    assert notes == []
