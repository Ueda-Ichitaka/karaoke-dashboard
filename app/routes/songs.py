"""About me: public song catalogue routes - search list, and each song's
expanded UltraStar metadata (including its cover image file)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse

from .. import songs as song_index
from .. import ultrastar
from ..config import settings
from ..deps import get_current_user, render
from ..models import User

router = APIRouter()

# Only these are ever served through the cover route, regardless of what
# #COVER: actually points at on disk.
_ALLOWED_COVER_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


def _entries_by_folder(songs: list[song_index.Song]) -> dict[str, list[ultrastar.SongMeta]]:
    return {song.folder: ultrastar.scan_folder_songs(song.folder) for song in songs}


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
        entries_by_folder=_entries_by_folder(result.items),
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
    return render(
        request, "_song_list.html", user, q=q, result=result,
        entries_by_folder=_entries_by_folder(result.items),
    )


@router.get("/songs/{folder}/cover/{filename}")
def song_cover(folder: str, filename: str):
    """Serve one song's cover image, strictly confined to its own folder."""
    song = song_index.get_by_folder(folder)
    if song is None:
        raise HTTPException(status_code=404)

    if "/" in filename or "\\" in filename or filename in (".", ".."):
        raise HTTPException(status_code=404)
    if Path(filename).suffix.lower() not in _ALLOWED_COVER_EXTS:
        raise HTTPException(status_code=404)

    folder_path = Path(settings.songs_dir) / song.folder
    try:
        resolved = (folder_path / filename).resolve(strict=True)
        folder_resolved = folder_path.resolve(strict=True)
    except OSError:
        raise HTTPException(status_code=404) from None
    if resolved.parent != folder_resolved or not resolved.is_file():
        raise HTTPException(status_code=404)

    return FileResponse(resolved, headers={"Cache-Control": "private, max-age=3600"})
