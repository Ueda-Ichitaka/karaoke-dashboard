"""About me: curated language choices, shared by the song-request form and
the broken-report form's language dropdowns - a hint for UltraSinger's
whisper transcription/repair (see UPSTREAM_REQUESTS.md), not the free-text
language parsed from library UltraStar files (see app/ultrastar.py). Mostly
ISO 639-1 codes, plus the app-level "mixed" pseudo-code for a song whose
lyrics switch languages mid-track.
"""

from __future__ import annotations

LANGUAGE_CHOICES: tuple[tuple[str, str], ...] = (
    ("", "Unspecified"),
    ("mixed", "Mixed"),
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

LANGUAGE_LABELS: dict[str, str] = dict(LANGUAGE_CHOICES)


def is_valid_language_code(code: str) -> bool:
    return code in LANGUAGE_CODES
