"""Request a new song (login required)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .. import songs
from ..database import get_db
from ..deps import render, require_user
from ..languages import LANGUAGE_CHOICES
from ..models import SongRequest, User
from ..validation import request_field_errors

router = APIRouter()


@router.get("/request")
def request_form(request: Request, user: User = Depends(require_user)):
    return render(
        request, "request.html", user,
        errors=[], form={}, submitted=False, language_choices=LANGUAGE_CHOICES,
    )


@router.get("/request/check")
def request_check(
    band_name: str = "",
    song_name: str = "",
    user: User = Depends(require_user),
):
    """Live "does this already exist?" lookup for the request form's JS."""
    band_name = band_name.strip()
    song_name = song_name.strip()
    folder = songs.folder_exists(band_name, song_name) if band_name and song_name else None
    return JSONResponse({"exists": folder is not None, "folder": folder})


@router.post("/request")
def request_submit(
    request: Request,
    band_name: str = Form(""),
    song_name: str = Form(""),
    youtube_url: str = Form(""),
    language: str = Form(""),
    musicbrainz_id: str = Form(""),
    lyrics_url: str = Form(""),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    band_name = band_name.strip()
    song_name = song_name.strip()
    youtube_url = youtube_url.strip()
    language = language.strip().lower()
    musicbrainz_id = musicbrainz_id.strip()
    lyrics_url = lyrics_url.strip()
    errors = request_field_errors(band_name, song_name, youtube_url, language)

    existing_folder = None
    if band_name and song_name:
        existing_folder = songs.folder_exists(band_name, song_name)
        if existing_folder:
            errors.append(
                f'"{band_name} - {song_name}" already appears to be in the library '
                f'(folder: "{existing_folder}").'
            )

    if errors:
        return render(
            request, "request.html", user, status_code=422,
            errors=errors,
            form={
                "band_name": band_name, "song_name": song_name, "youtube_url": youtube_url,
                "language": language, "musicbrainz_id": musicbrainz_id, "lyrics_url": lyrics_url,
            },
            submitted=False,
            language_choices=LANGUAGE_CHOICES,
        )

    db.add(
        SongRequest(
            band_name=band_name,
            song_name=song_name,
            youtube_url=youtube_url or None,
            language=language or None,
            musicbrainz_id=musicbrainz_id or None,
            lyrics_url=lyrics_url or None,
            requester_id=user.id,
            requester_username=user.username,
        )
    )
    db.commit()
    return render(
        request, "request.html", user,
        errors=[], form={}, submitted=True, language_choices=LANGUAGE_CHOICES,
        submitted_song=f"{band_name} - {song_name}",
    )
