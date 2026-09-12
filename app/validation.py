"""About me: shared song-request form validation used by both the public
request form (app/routes/requests.py) and its admin-side edit form
(app/routes/admin.py).
"""

from __future__ import annotations

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
