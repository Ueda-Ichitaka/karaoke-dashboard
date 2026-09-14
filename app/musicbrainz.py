"""About me: extracts a bare MusicBrainz ID (MBID) out of either the ID
itself or a pasted musicbrainz.org URL, for the "MusicBrainz ID"
request/report field. The field's tooltip already promises "either works,
it's auto-detected" - this makes that true. Also protects the DB column: a
pasted URL is typically 60-80+ characters, well past VARCHAR(64).
"""

from __future__ import annotations

import re

_MBID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")

MAX_LENGTH = 64


def extract_musicbrainz_id(value: str) -> str:
    """Pull the bare MBID out of a pasted value - a URL or the ID itself.

    Free text that isn't a URL and has no recognizable MBID in it (e.g. a
    placeholder ID used before the real one is known) passes through
    unchanged - this field is best-effort, not strictly validated.
    """
    value = value.strip()
    match = _MBID_RE.search(value)
    return match.group(0).lower() if match else value
