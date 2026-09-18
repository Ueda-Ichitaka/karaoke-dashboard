"""Tests for the "Mixed" language option (a song whose lyrics switch
languages mid-track) - see app/languages.py.
"""

from __future__ import annotations

from app.languages import LANGUAGE_CHOICES, LANGUAGE_LABELS, is_valid_language_code


def test_mixed_is_a_valid_language_code():
    assert is_valid_language_code("mixed")


def test_mixed_is_offered_in_the_choice_list():
    codes = [code for code, _ in LANGUAGE_CHOICES]
    assert "mixed" in codes


def test_language_labels_maps_mixed_to_a_readable_name():
    assert LANGUAGE_LABELS["mixed"] == "Mixed"
