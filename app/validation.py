"""About me: shared form validation for the song-request form (public and
admin-side edit) and the broken-song report form (app/routes/requests.py,
app/routes/admin.py, app/routes/reports.py).
"""

from __future__ import annotations

from .broken_categories import is_valid_category
from .languages import is_valid_language_code


def is_http_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def request_field_errors(band_name: str, song_name: str, youtube_url: str, language: str) -> list[str]:
    errors: list[str] = []
    if not band_name:
        errors.append("Band name is required.")
    if not song_name:
        errors.append("Song name is required.")
    if youtube_url and not is_http_url(youtube_url):
        errors.append("The YouTube link must start with http:// or https://")
    if language and not is_valid_language_code(language):
        errors.append("Unrecognized language.")
    return errors


def broken_report_field_errors(category: str, description: str) -> list[str]:
    errors: list[str] = []
    if not category:
        errors.append("Please choose a category.")
    elif not is_valid_category(category):
        errors.append("Unrecognized category.")
    if category == "other" and not description:
        errors.append("Please describe what's broken.")
    return errors
