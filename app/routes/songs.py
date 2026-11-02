"""About me: public song catalogue routes - the searchable song list (each
song marked when it's known to be broken, see app/known_broken.py, for as
long as the Settings page's badge mode says - app/broken_badge.py) with
each song's expanded UltraStar metadata (including its cover image file),
the "What's new" page: the songs added and the songs updated within the
period set on the Settings page (app/recent_period.py; as recorded by the
library scan, app/library_history.py), narrowed by its own search, and the
Genres page for logged-in users: the genres the library scan read from the
song files (app/song_genres.py) with their song counts, and the songs of
the picked genre, narrowed by a search over genre, band and title."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from .. import songs as song_index
from .. import ultrastar
from ..app_settings import get_app_settings
from ..broken_badge import UNTIL_UPDATED
from ..config import settings
from ..database import get_db
from ..deps import get_current_user, render, require_user
from ..known_broken import known_broken
from ..library_history import recent_additions, recent_updates
from ..models import User
from ..recent_period import describe, period_start
from ..song_genres import companions, genre_counts, genres_by_folder, search_with_genres

router = APIRouter()

# Only these are ever served through the cover route, regardless of what
# #COVER: actually points at on disk.
_ALLOWED_COVER_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


def _broken(db: Session) -> dict[str, str]:
    """The songs to badge as broken, by the badge mode set on the Settings page."""
    return known_broken(db, until_updated=get_app_settings(db).broken_badge == UNTIL_UPDATED)


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
    db: Session = Depends(get_db),
):
    result = song_index.search(q, page)
    return render(
        request, "songs.html", user,
        q=q, result=result, total=song_index.total_count(),
        entries_by_folder=_entries_by_folder(result.items), broken=_broken(db),
    )


@router.get("/songs/partial")
def song_list_partial(
    request: Request,
    q: str = "",
    page: int = 1,
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List fragment used for the live-search results (no page chrome)."""
    result = song_index.search(q, page)
    return render(
        request, "_song_list.html", user, q=q, result=result,
        entries_by_folder=_entries_by_folder(result.items), broken=_broken(db),
    )


def _whats_new(request: Request, template: str, q: str, user: User | None, db: Session):
    songs = song_index.filter_songs(song_index.all_songs(), q)
    app_settings = get_app_settings(db)
    since = period_start(datetime.now(UTC), app_settings.recent_amount, app_settings.recent_unit)
    return render(
        request, template, user, q=q, broken=_broken(db),
        recent_period=describe(app_settings.recent_amount, app_settings.recent_unit),
        recent_added=recent_additions(db, songs, since), recent_updated=recent_updates(db, songs, since),
    )


@router.get("/new")
def whats_new(
    request: Request,
    q: str = "",
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _whats_new(request, "new.html", q, user, db)


@router.get("/new/partial")
def whats_new_partial(
    request: Request,
    q: str = "",
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Both panels, used for the live-search results (no page chrome)."""
    return _whats_new(request, "_new_panels.html", q, user, db)


def _genres_page(request: Request, template: str, q: str, genre: str, page: int, user: User, db: Session):
    songs = song_index.all_songs()
    genres = genres_by_folder(db, songs)
    matches = search_with_genres(songs, genres, q)
    listed = [song for song in matches if genre in genres[song.folder]] if genre else matches
    genre_list = genre_counts(matches, genres)
    return render(
        request, template, user, q=q, genre=genre, genres=genres, genre_list=genre_list,
        top_count=max((count for _, count in genre_list), default=0),
        companions=companions(matches, genres, genre) if genre else [],
        result=song_index.paginate(listed, page), total=len(songs), with_genre=len(genres),
    )


@router.get("/genres")
def genres_page(
    request: Request,
    q: str = "",
    genre: str = "",
    page: int = 1,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return _genres_page(request, "genres.html", q, genre, page, user, db)


@router.get("/genres/partial")
def genres_partial(
    request: Request,
    q: str = "",
    genre: str = "",
    page: int = 1,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """The genre list and the song list, used for the live-search results (no page chrome)."""
    return _genres_page(request, "_genre_panels.html", q, genre, page, user, db)


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
