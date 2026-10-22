"""About me: shared form validation for the song-request form (public and
admin-side edit) and the broken-song report form (app/routes/requests.py,
app/routes/admin.py, app/routes/reports.py). A request's YouTube field takes
an http(s) link; a lyrics field (request lyrics_url, report genius_url)
only a genius.com song page or an lrclib.net track page - the pages the
song pipeline can use. The admin side (edit forms, admit checks, CSV
imports) passes allow_file_paths, which also takes a path to an .mp3/.mp4
file in the YouTube field and to a .txt file in a lyrics field.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from .broken_categories import is_valid_category
from .duet import is_valid_duet
from .languages import is_valid_language_code
from .musicbrainz import MAX_LENGTH as MUSICBRAINZ_ID_MAX_LENGTH
from .profiles import report_required_fields, request_required_fields

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


MEDIA_PATH_EXTENSIONS = (".mp3", ".mp4")
LYRICS_PATH_EXTENSIONS = (".txt",)

_GENIUS_HOSTS = {"genius.com", "www.genius.com"}
_LRCLIB_HOSTS = {"lrclib.net", "www.lrclib.net"}
_GENIUS_SONG_PATH_RE = re.compile(r"^/[^/]+-lyrics/?$", re.IGNORECASE)
_LRCLIB_TRACK_PATH_RE = re.compile(r"^/tracks/\d+/?$")


def is_file_path(value: str, extensions: tuple[str, ...]) -> bool:
    """A file path (not a URL of any scheme) ending in one of the extensions."""
    return "://" not in value and value.lower().endswith(extensions)


def is_lyrics_link(value: str) -> bool:
    """A genius.com song page (genius.com/...-lyrics) or an lrclib.net track
    page (lrclib.net/tracks/<number>), over http(s)."""
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https"):
        return False
    if parts.hostname in _GENIUS_HOSTS:
        return bool(_GENIUS_SONG_PATH_RE.match(parts.path))
    if parts.hostname in _LRCLIB_HOSTS:
        return bool(_LRCLIB_TRACK_PATH_RE.match(parts.path))
    return False


def youtube_link_error(value: str, allow_file_paths: bool) -> str | None:
    if not value or is_http_url(value):
        return None
    if not allow_file_paths:
        return "The YouTube link must start with http:// or https://"
    if not is_file_path(value, MEDIA_PATH_EXTENSIONS):
        return "The YouTube link must start with http:// or https://, or be a path to an .mp3 or .mp4 file."
    return None


def lyrics_link_error(value: str, allow_file_paths: bool) -> str | None:
    if not value or is_lyrics_link(value):
        return None
    if not allow_file_paths:
        return ("The lyrics link must be a genius.com song page (genius.com/...-lyrics) "
                "or an lrclib.net track page (lrclib.net/tracks/...).")
    if not is_file_path(value, LYRICS_PATH_EXTENSIONS):
        return ("The lyrics link must be a genius.com song page (genius.com/...-lyrics), "
                "an lrclib.net track page (lrclib.net/tracks/...) or a path to a .txt file.")
    return None


def request_field_errors(
    band_name: str, song_name: str, youtube_url: str, language: str, musicbrainz_id: str = "",
    cover_url: str = "", duet: str = "", lyrics_url: str = "", profile: str = "karaoke_night",
    required: set[str] | None = None, allow_file_paths: bool = False,
) -> list[str]:
    """`required` overrides the profile lookup entirely when given - used by
    the admit-time check (app/routes/admin.py), which has its own fixed set
    of required fields independent of the request-form profile switch.
    allow_file_paths lets the YouTube field hold an .mp3/.mp4 file path and
    the lyrics field a .txt file path.
    """
    required = required if required is not None else request_required_fields(profile)
    errors: list[str] = []
    if not band_name:
        errors.append("Band name is required.")
    if not song_name:
        errors.append("Song name is required.")
    if "youtube_url" in required and not youtube_url:
        errors.append("YouTube link is required.")
    if error := youtube_link_error(youtube_url, allow_file_paths):
        errors.append(error)
    if "language" in required and not language:
        errors.append("Please choose the song's language.")
    if language and not is_valid_language_code(language):
        errors.append("Unrecognized language.")
    if "musicbrainz_id" in required and not musicbrainz_id:
        errors.append("MusicBrainz ID is required.")
    if len(musicbrainz_id) > MUSICBRAINZ_ID_MAX_LENGTH:
        errors.append(
            f"Unrecognized MusicBrainz ID - paste the ID itself or a musicbrainz.org "
            f"link to it (max {MUSICBRAINZ_ID_MAX_LENGTH} characters)."
        )
    if "lyrics_url" in required and not lyrics_url:
        errors.append("Lyrics link is required.")
    if error := lyrics_link_error(lyrics_url, allow_file_paths):
        errors.append(error)
    if cover_url and not is_http_url(cover_url):
        errors.append("The cover image link must start with http:// or https://")
    if duet and not is_valid_duet(duet):
        errors.append("Unrecognized duet choice.")
    return errors


def broken_report_field_errors(
    category: str, description: str, genius_url: str = "", language: str = "", cover_url: str = "",
    profile: str = "strict", required: set[str] | None = None, allow_file_paths: bool = False,
) -> list[str]:
    """`required` overrides the profile lookup entirely when given - used by
    the admin edit form and admit gate (app/routes/admin.py), which have
    their own fixed set of required fields independent of the profile.
    allow_file_paths lets the lyrics link be a .txt file path.
    """
    required = required if required is not None else report_required_fields(profile, category)
    errors: list[str] = []
    if not category:
        errors.append("Please choose a category.")
    elif not is_valid_category(category):
        errors.append("Unrecognized category.")
    if "description" in required and not description:
        errors.append("Please describe what's broken.")
    if "genius_url" in required and not genius_url:
        errors.append("Please provide a genius.com or lrclib.net lyrics link.")
    if error := lyrics_link_error(genius_url, allow_file_paths):
        errors.append(error)
    if "language" in required and not language:
        errors.append("Please choose the song's language.")
    elif language and not is_valid_language_code(language):
        errors.append("Unrecognized language.")
    if "cover_url" in required and not cover_url:
        errors.append("Please provide a cover image link for this category.")
    if cover_url and not is_http_url(cover_url):
        errors.append("The cover image link must start with http:// or https://")
    return errors
