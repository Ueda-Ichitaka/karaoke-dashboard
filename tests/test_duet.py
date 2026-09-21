"""Tests for the request form's yes/no/blank Duet choice - see app/duet.py."""

from __future__ import annotations

from app.duet import DUET_CHOICES, DUET_LABELS, is_valid_duet


def test_yes_and_no_are_valid():
    assert is_valid_duet("yes")
    assert is_valid_duet("no")


def test_anything_else_is_invalid():
    assert not is_valid_duet("maybe")
    assert not is_valid_duet("")


def test_choices_start_with_the_blank_option():
    assert DUET_CHOICES[0][0] == ""
    assert DUET_LABELS["yes"] == "Yes"
    assert DUET_LABELS["no"] == "No"
