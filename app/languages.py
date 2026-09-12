"""About me: curated ISO 639-1 language choices for the song-request form's
language dropdown - a hint for UltraSinger's whisper transcription (see
UPSTREAM_REQUESTS.md), not the free-text language parsed from library
UltraStar files (see app/ultrastar.py). Single-language only for now; a
song whose lyrics switch languages mid-track has no representation here
yet.
"""

from __future__ import annotations

LANGUAGE_CHOICES: tuple[tuple[str, str], ...] = (
    ("", "Unspecified"),
    ("de", "German"),
    ("en", "English"),
    ("fr", "French"),
    ("es", "Spanish"),
    ("it", "Italian"),
    ("pt", "Portuguese"),
    ("nl", "Dutch"),
    ("pl", "Polish"),
    ("ru", "Russian"),
    ("sv", "Swedish"),
    ("da", "Danish"),
    ("no", "Norwegian"),
    ("fi", "Finnish"),
    ("tr", "Turkish"),
    ("ja", "Japanese"),
    ("ko", "Korean"),
    ("zh", "Chinese"),
)

LANGUAGE_CODES: frozenset[str] = frozenset(code for code, _ in LANGUAGE_CHOICES if code)


def is_valid_language_code(code: str) -> bool:
    return code in LANGUAGE_CODES
