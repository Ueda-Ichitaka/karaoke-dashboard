"""Public song catalogue with search."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from .. import songs as song_index
from ..deps import get_current_user, render
from ..models import User

router = APIRouter()


@router.get("/")
def index():
    return RedirectResponse("/songs", status_code=303)


@router.get("/healthz")
def healthz():
    return {"status": "ok"}


@router.get("/songs")
def song_list(
    request: Request,
    q: str = "",
    page: int = 1,
    user: User | None = Depends(get_current_user),
):
    result = song_index.search(q, page)
    return render(
        request, "songs.html", user,
        q=q, result=result, total=song_index.total_count(),
    )


@router.get("/songs/partial")
def song_list_partial(
    request: Request,
    q: str = "",
    page: int = 1,
    user: User | None = Depends(get_current_user),
):
    """List fragment used for the live-search results (no page chrome)."""
    result = song_index.search(q, page)
    return render(request, "_song_list.html", user, q=q, result=result)
