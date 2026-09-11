"""Request a new song (login required)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import render, require_user
from ..models import SongRequest, User

router = APIRouter()


def _valid_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


@router.get("/request")
def request_form(request: Request, user: User = Depends(require_user)):
    return render(request, "request.html", user, errors=[], form={}, submitted=False)


@router.post("/request")
def request_submit(
    request: Request,
    band_name: str = Form(""),
    song_name: str = Form(""),
    youtube_url: str = Form(""),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    band_name = band_name.strip()
    song_name = song_name.strip()
    youtube_url = youtube_url.strip()
    errors: list[str] = []

    if not band_name:
        errors.append("Band name is required.")
    if not song_name:
        errors.append("Song name is required.")
    if youtube_url and not _valid_url(youtube_url):
        errors.append("The YouTube link must start with http:// or https://")

    if errors:
        return render(
            request, "request.html", user, status_code=422,
            errors=errors,
            form={"band_name": band_name, "song_name": song_name, "youtube_url": youtube_url},
            submitted=False,
        )

    db.add(
        SongRequest(
            band_name=band_name,
            song_name=song_name,
            youtube_url=youtube_url or None,
            requester_id=user.id,
            requester_username=user.username,
        )
    )
    db.commit()
    return render(
        request, "request.html", user,
        errors=[], form={}, submitted=True,
        submitted_song=f"{band_name} - {song_name}",
    )
