"""About me: shared form validation for the song-request form (public and
admin-side edit) and the broken-song report form (app/routes/requests.py,
app/routes/admin.py, app/routes/reports.py).
"""

from __future__ import annotations

import re

from .broken_categories import is_valid_category
from .duet import is_valid_duet
from .languages import is_valid_language_code
from .musicbrainz import MAX_LENGTH as MUSICBRAINZ_ID_MAX_LENGTH

_LINE_BREAK_RE = re.compile(r"[\r\n\x0b\x0c]+")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0e-\x1f\x7f]")
_RISKY_CHARS_RE = re.compile(r'[,;"|\\]')
_LEADING_FORMULA_RE = re.compile(r"^[=+\-@]+")


def sanitize_free_text(value: str) -> str:
    """Collapse free text to a single line and strip characters that could
    break broken.csv's row formatting (a stray comma/semicolon/quote) or
    trigger spreadsheet formula injection when opened in Excel/Sheets (a
    leading =, +, -, or @) - applied at submission time (app/routes/reports.py)
    so the stored value is safe everywhere it's later shown or exported, not
    just in the CSV writer.
    """
    value = _LINE_BREAK_RE.sub(" ", value)
    value = _CONTROL_RE.sub("", value)
    value = _RISKY_CHARS_RE.sub("", value)
    value = _LEADING_FORMULA_RE.sub("", value.strip())
    return " ".join(value.split())


_FORMULA_TRIGGER_CHARS = ("=", "+", "-", "@")


def neutralize_csv_formula(value: str) -> str:
    """Defuse CSV/spreadsheet formula injection (OWASP) for a value that's
    otherwise left as-is (unlike sanitize_free_text, this doesn't strip
    commas/quotes - csv.writer already RFC4180-quotes those correctly, and
    this is used on identity fields like a band/song name where stripping
    real characters would be destructive). A leading =, +, - or @ makes
    Excel/Sheets evaluate the cell as a formula when the CSV is opened - a
    single-quote prefix forces it to be read as plain text instead, the
    standard, non-destructive mitigation.
    """
    if value and value[0] in _FORMULA_TRIGGER_CHARS:
        return "'" + value
    return value


def is_http_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def request_field_errors(
    band_name: str, song_name: str, youtube_url: str, language: str, musicbrainz_id: str = "",
    cover_url: str = "", duet: str = "",
) -> list[str]:
    errors: list[str] = []
    if not band_name:
        errors.append("Band name is required.")
    if not song_name:
        errors.append("Song name is required.")
    if youtube_url and not is_http_url(youtube_url):
        errors.append("The YouTube link must start with http:// or https://")
    if language and not is_valid_language_code(language):
        errors.append("Unrecognized language.")
    if len(musicbrainz_id) > MUSICBRAINZ_ID_MAX_LENGTH:
        errors.append(
            f"Unrecognized MusicBrainz ID - paste the ID itself or a musicbrainz.org "
            f"link to it (max {MUSICBRAINZ_ID_MAX_LENGTH} characters)."
        )
    if cover_url and not is_http_url(cover_url):
        errors.append("The cover image link must start with http:// or https://")
    if duet and not is_valid_duet(duet):
        errors.append("Unrecognized duet choice.")
    return errors


_GENIUS_REQUIRED_CATEGORIES = frozenset({"lyrics", "async"})


def broken_report_field_errors(
    category: str, description: str, genius_url: str = "", language: str = "", cover_url: str = ""
) -> list[str]:
    errors: list[str] = []
    if not category:
        errors.append("Please choose a category.")
    elif not is_valid_category(category):
        errors.append("Unrecognized category.")
    if category == "other" and not description:
        errors.append("Please describe what's broken.")
    if category in _GENIUS_REQUIRED_CATEGORIES and not genius_url:
        errors.append('Please provide a genius.com lyrics link for this category.')
    if genius_url and not is_http_url(genius_url):
        errors.append("The lyrics link must start with http:// or https://")
    if not language:
        errors.append("Please choose the song's language.")
    elif not is_valid_language_code(language):
        errors.append("Unrecognized language.")
    if cover_url and not is_http_url(cover_url):
        errors.append("The cover image link must start with http:// or https://")
    return errors
