"""About me: the "karaoke night" vs "strict" required-field rules for the
public request-song and report-broken forms, and for the strict admission
check a pending entry must pass before an admin can move it into the
exportable list (see app/routes/admin.py's admit routes). The two views
switch independently - each has its own profile, set in the admin Settings
view (app/routes/admin.py, app/models.py: AppSettings).
"""

from __future__ import annotations

PROFILE_CHOICES: tuple[tuple[str, str], ...] = (
    ("karaoke_night", "Karaoke night"),
    ("strict", "Strict"),
)

PROFILE_CODES: frozenset[str] = frozenset(code for code, _ in PROFILE_CHOICES)

# Categories that, under the strict profile, also require a lyrics link -
# same set app/validation.py's broken_report_field_errors already used.
_GENIUS_REQUIRED_CATEGORIES = frozenset({"lyrics", "async"})


def request_required_fields(profile: str) -> set[str]:
    """Which request-form fields are mandatory under the given profile.

    Band/song are always required, in both profiles. Strict additionally
    requires a YouTube link, language, and lyrics link. MusicBrainz ID,
    cover image link, and Duet are never required by either profile.
    """
    required = {"band_name", "song_name"}
    if profile == "strict":
        required |= {"youtube_url", "language", "lyrics_url"}
    return required


def report_required_fields(profile: str, category: str) -> set[str]:
    """Which report-form fields are mandatory under the given profile.

    The song picker, category and "what's broken?" description are always
    required, in both profiles. Strict additionally requires the language,
    plus a lyrics link for the categories that already call for one
    (app/broken_categories.py). Cover image link is never required.
    """
    required = {"song_folder", "category", "description"}
    if profile == "strict":
        required.add("language")
        if category in _GENIUS_REQUIRED_CATEGORIES:
            required.add("genius_url")
    return required
