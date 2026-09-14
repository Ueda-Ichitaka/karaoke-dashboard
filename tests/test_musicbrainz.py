"""Tests for app/musicbrainz.py: extracting a bare MusicBrainz ID (MBID) out
of either the ID itself or a pasted musicbrainz.org URL. A pasted URL used
to overflow the musicbrainz_id column (VARCHAR(64)) and crash the request
with a 500 - the field's own tooltip already promised "either works, it's
auto-detected", so this makes that actually true instead of just accepting
whatever fits and crashing on whatever doesn't.
"""

from __future__ import annotations

from app.musicbrainz import extract_musicbrainz_id


def test_extracts_id_from_a_recording_url():
    url = "https://musicbrainz.org/recording/2fa14ea5-9e94-4a6c-9c62-3c0dc9ce6b8f"
    assert extract_musicbrainz_id(url) == "2fa14ea5-9e94-4a6c-9c62-3c0dc9ce6b8f"


def test_extracts_id_from_a_release_url_with_query_string():
    url = "https://musicbrainz.org/release/2fa14ea5-9e94-4a6c-9c62-3c0dc9ce6b8f?srsltid=abc"
    assert extract_musicbrainz_id(url) == "2fa14ea5-9e94-4a6c-9c62-3c0dc9ce6b8f"


def test_bare_id_passes_through_unchanged():
    assert extract_musicbrainz_id("2fa14ea5-9e94-4a6c-9c62-3c0dc9ce6b8f") == "2fa14ea5-9e94-4a6c-9c62-3c0dc9ce6b8f"


def test_uppercase_id_in_url_is_lowercased():
    url = "https://musicbrainz.org/recording/2FA14EA5-9E94-4A6C-9C62-3C0DC9CE6B8F"
    assert extract_musicbrainz_id(url) == "2fa14ea5-9e94-4a6c-9c62-3c0dc9ce6b8f"


def test_free_text_without_a_recognizable_id_passes_through():
    # existing free-text IDs already in use/tested elsewhere must keep working
    assert extract_musicbrainz_id("mbid-123") == "mbid-123"


def test_strips_surrounding_whitespace():
    assert extract_musicbrainz_id("  mbid-123  ") == "mbid-123"
