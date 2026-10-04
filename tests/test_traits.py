"""Tests for app/traits.py: the fixed, still-growing vocal/instrument trait
choice list an admin can tag a request/report with when reviewing it (one
trait at a time - see app/models.py's SongRequest.trait/BrokenReport.trait).
"none" means no trait was set.
"""

from __future__ import annotations

from app.traits import DEFAULT_TRAIT, TRAIT_CHOICES, is_valid_trait


def test_trait_choices_include_the_requested_list():
    codes = [code for code, _ in TRAIT_CHOICES]
    assert codes == ["none", "harsh_vocals", "operatic_vocals", "loud_high_instruments", "choir"]


def test_is_valid_trait():
    assert is_valid_trait("choir")
    assert not is_valid_trait("not-a-trait")


def test_default_trait_is_none():
    assert DEFAULT_TRAIT == "none"
