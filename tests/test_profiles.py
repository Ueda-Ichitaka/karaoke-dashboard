"""Tests for app/profiles.py: the karaoke-night/strict required-field rules
for the request-song and report-broken forms (app/routes/requests.py,
app/routes/reports.py), each switched independently via the admin Settings
view (app/routes/admin.py).
"""

from __future__ import annotations

from app.profiles import (
    PROFILE_CHOICES,
    report_required_fields,
    request_required_fields,
)


def test_profile_choices_are_karaoke_night_and_strict():
    assert PROFILE_CHOICES == (("karaoke_night", "Karaoke night"), ("strict", "Strict"))


# ------------------------------------------------------------ request form
def test_karaoke_night_request_only_requires_band_and_song():
    assert request_required_fields("karaoke_night") == {"band_name", "song_name"}


def test_strict_request_requires_band_song_youtube_language_lyrics():
    assert request_required_fields("strict") == {
        "band_name", "song_name", "youtube_url", "language", "lyrics_url",
    }


# ------------------------------------------------------------- report form
def test_karaoke_night_report_only_requires_song_category_description():
    assert report_required_fields("karaoke_night", category="lyrics") == {
        "song_folder", "category", "description",
    }
    # even for a genius-required category, karaoke-night relaxes it
    assert "genius_url" not in report_required_fields("karaoke_night", category="async")


def test_strict_report_requires_song_category_language_description():
    required = report_required_fields("strict", category="audio")
    assert required == {"song_folder", "category", "language", "description"}


def test_strict_report_also_requires_genius_url_for_specific_categories():
    for category in ("lyrics", "async"):
        assert "genius_url" in report_required_fields("strict", category=category)
    for category in ("gap", "video", "audio", "other"):
        assert "genius_url" not in report_required_fields("strict", category=category)
