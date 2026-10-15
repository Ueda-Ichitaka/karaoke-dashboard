"""About me: imports song requests from a CSV in the existing
song-requests.csv export format (band name, song name, youtube link,
language, musicbrainz_id, lyrics_url, cover_url, duet, genre, trait - see
app/routes/admin.py: requests_csv), for the admin "Import CSV" upload on
the Requested page.

Each usable row becomes a PendingSongRequest (Needs review), never an
admitted one - an admin still reviews, completes and admits it. A song never
gets a second request: a row with the same band, song and duet setting as a
pending or open request (app/request_matching.py: find_existing_request,
the public form's duplicate check) - including an earlier row of the same
file - is merged into it by the shared import rules (app/import_merge.py).
Rows are skipped with a reason when the song is already in the library (an
exact "band - song" folder, as the public form refuses it), when the same
request is already done, or when a value is unusable (the public form's
own checks: app/validation.py: request_field_errors); the rest still import.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import duplicates, songs
from .duet import wants_duet
from .genres import DEFAULT_GENRE, format_genres, is_valid_genre
from .import_merge import (
    ImportNote,
    ImportResult,
    SkippedRow,
    keep_or_fill,
    merge_codes,
    parse_codes,
    preferred_lyrics_link,
    read_rows,
)
from .models import PendingSongRequest, SongRequest, User
from .musicbrainz import extract_musicbrainz_id
from .request_matching import find_existing_request
from .traits import DEFAULT_TRAIT, format_traits, is_valid_trait
from .validation import request_field_errors

COLUMNS = (
    "band name", "song name", "youtube link", "language", "musicbrainz_id", "lyrics_url", "cover_url", "duet",
    "genre", "trait",
)
_HEADER_FIRST_CELLS = {"band", "band name"}


def _is_done(db: Session, band_name: str, song_name: str, duet: str) -> bool:
    band, song = duplicates.normalize_key(band_name), duplicates.normalize_key(song_name)
    for row in db.scalars(select(SongRequest).where(SongRequest.status == "done")):
        if (duplicates.normalize_key(row.band_name) == band and duplicates.normalize_key(row.song_name) == song
                and wants_duet(row.duet) == wants_duet(duet)):
            return True
    return False


def _merge(existing: PendingSongRequest | SongRequest, values: dict[str, str], genres: list[str],
           traits: list[str]) -> list[str]:
    """Merges one row into the song's existing request; returns the notes."""
    notes: list[str] = []
    existing.youtube_url = keep_or_fill(existing.youtube_url, values["youtube link"], "YouTube link", notes)
    existing.language = keep_or_fill(existing.language, values["language"], "language", notes)
    existing.musicbrainz_id = keep_or_fill(existing.musicbrainz_id, values["musicbrainz_id"], "MusicBrainz ID", notes)
    existing.lyrics_url = preferred_lyrics_link(existing.lyrics_url, values["lyrics_url"])
    existing.cover_url = keep_or_fill(existing.cover_url, values["cover_url"], "cover link", notes)
    existing.duet = keep_or_fill(existing.duet, values["duet"], "duet", notes)
    existing.genre = merge_codes(existing.genre, genres, DEFAULT_GENRE)
    existing.trait = merge_codes(existing.trait, traits, DEFAULT_TRAIT)
    return notes


def import_requests(db: Session, text: str, user: User) -> ImportResult:
    result = ImportResult()
    for line, values in read_rows(text, COLUMNS, _HEADER_FIRST_CELLS):
        for key in ("language", "duet"):
            values[key] = values[key].lower()
        values["musicbrainz_id"] = extract_musicbrainz_id(values["musicbrainz_id"])
        band, song = values["band name"], values["song name"]

        errors = request_field_errors(
            band, song, values["youtube link"], values["language"], values["musicbrainz_id"], values["cover_url"],
            values["duet"], lyrics_url=values["lyrics_url"], required=set(),
        )
        genres, genre_error = parse_codes(values["genre"], is_valid_genre, "genre")
        traits, trait_error = parse_codes(values["trait"], is_valid_trait, "trait")
        errors += [e for e in (genre_error, trait_error) if e]
        if errors:
            result.skipped.append(SkippedRow(line, " ".join(errors)))
            continue
        folder = songs.folder_exists(band, song)
        if folder is not None:
            reason = f'"{band} - {song}" is already in the library (folder: "{folder}").'
            result.skipped.append(SkippedRow(line, reason))
            continue

        existing = find_existing_request(db, band, song, values["duet"])
        if existing is not None:
            notes = _merge(existing, values, genres, traits)
            label = f"{existing.band_name} - {existing.song_name}"
            result.notes.extend(ImportNote(line, f"{label}: {note}") for note in notes)
            result.merged += 1
        elif _is_done(db, band, song, values["duet"]):
            result.skipped.append(SkippedRow(line, f'The request for "{band} - {song}" is already done.'))
            continue
        else:
            db.add(
                PendingSongRequest(
                    band_name=band,
                    song_name=song,
                    youtube_url=values["youtube link"] or None,
                    language=values["language"] or None,
                    musicbrainz_id=values["musicbrainz_id"] or None,
                    lyrics_url=values["lyrics_url"] or None,
                    cover_url=values["cover_url"] or None,
                    duet=values["duet"] or None,
                    genre=format_genres(genres),
                    trait=format_traits(traits),
                    requester_id=user.id,
                    requester_username=user.username,
                )
            )
            result.imported += 1
        db.flush()  # a later row for the same song must find this one
    db.commit()
    return result
