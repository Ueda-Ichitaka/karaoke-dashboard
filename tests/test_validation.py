"""Tests for app/validation.py's sanitize_free_text: collapses free text to
a single line and strips characters that could break CSV row formatting
(broken.csv - see app/routes/admin.py: reports_csv) or trigger spreadsheet
formula injection when a report's description is later opened in Excel/
Sheets.
"""

from __future__ import annotations

from app.validation import neutralize_csv_formula, sanitize_free_text


def test_line_breaks_are_collapsed_to_a_single_line():
    assert sanitize_free_text("line one\nline two\r\nline three") == "line one line two line three"


def test_commas_and_semicolons_are_stripped():
    assert sanitize_free_text("audio cuts out, sometimes; badly") == "audio cuts out sometimes badly"


def test_quotes_and_pipes_and_backslashes_are_stripped():
    assert sanitize_free_text('a "b" | c \\ d') == "a b c d"


def test_leading_formula_trigger_characters_are_stripped():
    assert sanitize_free_text("=SUM(A1:A10)") == "SUM(A1:A10)"
    assert sanitize_free_text("+1 to this") == "1 to this"
    assert sanitize_free_text("@mention") == "mention"
    assert sanitize_free_text("-1 second offset") == "1 second offset"


def test_control_characters_are_stripped():
    assert sanitize_free_text("bad\x00null\x07bell") == "badnullbell"


def test_whitespace_is_collapsed_and_trimmed():
    assert sanitize_free_text("  too    many   spaces  ") == "too many spaces"


def test_plain_text_is_unaffected():
    assert sanitize_free_text("the lyrics drift out of sync after minute 2") == \
        "the lyrics drift out of sync after minute 2"


# ------------------------------------------------------ CSV formula injection
def test_neutralize_csv_formula_prefixes_a_leading_equals():
    assert neutralize_csv_formula('=cmd|"/c calc"!A0') == '\'=cmd|"/c calc"!A0'


def test_neutralize_csv_formula_prefixes_leading_plus_minus_at():
    assert neutralize_csv_formula("+1+1") == "'+1+1"
    assert neutralize_csv_formula("-1+1") == "'-1+1"
    assert neutralize_csv_formula("@SUM(1,2)") == "'@SUM(1,2)"


def test_neutralize_csv_formula_leaves_ordinary_text_untouched():
    assert neutralize_csv_formula("Guns N' Roses") == "Guns N' Roses"
    assert neutralize_csv_formula("AC/DC") == "AC/DC"
    assert neutralize_csv_formula("") == ""


def test_neutralize_csv_formula_does_not_touch_a_mid_string_trigger_char():
    assert neutralize_csv_formula("Earth, Wind & Fire") == "Earth, Wind & Fire"
