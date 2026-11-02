"""About me: public song catalogue routes - the searchable song list (each
song marked when it's known to be broken, see app/known_broken.py, for as
long as the Settings page's badge mode says - app/broken_badge.py) with
each song's expanded UltraStar metadata (including its cover image file),
the "What's new" page: the songs added and the songs updated within the
period set on the Settings page (app/recent_period.py; as recorded by the
library scan, app/library_history.py), narrowed by its own search, and the
Genres page for logged-in users: the genres the library scan read from the
song files (app/song_genres.py) with their song counts, and the songs of
the picked genre, narrowed by a search over genre, band and title. Its
Map and Connections tabs draw the same genres as SVG (app/genre_layout.py,
as many as the Settings page's "Genres on the map") and mark the songs the
search finds. Its Edit tab, for contributors and admins, lists every song
with its genres to change them (app/song_genres.py: the edit stands in for
the file's genres on every tab until a library scan reads the same from the
files) and exports the open edits for the USDX Song Factory."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from .. import songs as song_index
from .. import ultrastar
from ..app_settings import get_app_settings
from ..broken_badge import UNTIL_UPDATED
from ..config import settings
from ..database import get_db
from ..deps import get_current_user, render, require_contributor, require_user
from ..genre_layout import genre_map, genre_network
from ..known_broken import known_broken
from ..library_history import recent_additions, recent_updates
from ..models import User
from ..recent_period import describe, period_start
from ..song_genres import (
    companions,
    current_genres,
    file_genres_by_folder,
    folder_file_genres,
    genre_counts,
    genre_edit_lines,
    genres_by_folder,
    open_edits,
    reset_genre_edit,
    save_genre_edit,
    search_with_genres,
)

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


# The Genres page's tabs: key, label, address; the Edit tab only for contributors and admins.
GENRE_TABS = (("list", "List", "/genres"), ("map", "Map", "/genres/map"),
              ("connections", "Connections", "/genres/connections"))
EDIT_TAB = ("edit", "Edit", "/genres/edit")


def _tab_context(tab: str, songs: list[song_index.Song], genres: dict[str, list[str]], user: User) -> dict:
    """What the head every Genres tab shares (_genre_head.html) needs."""
    tabs = GENRE_TABS + ((EDIT_TAB,) if user.can_contribute else ())
    return {"tab": tab, "tab_url": dict((key, url) for key, _, url in tabs)[tab], "genre_tabs": tabs,
            "total": len(songs), "with_genre": len(genres)}


def _genres_page(request: Request, template: str, q: str, genre: str, page: int, user: User, db: Session):
    songs = song_index.all_songs()
    genres = genres_by_folder(db, songs)
    matches = search_with_genres(songs, genres, q)
    listed = [song for song in matches if genre in genres[song.folder]] if genre else matches
    genre_list = genre_counts(matches, genres)
    return render(
        request, template, user, **_tab_context("list", songs, genres, user),
        q=q, genre=genre, genres=genres, genre_list=genre_list,
        top_count=max((count for _, count in genre_list), default=0),
        companions=companions(matches, genres, genre) if genre else [],
        result=song_index.paginate(listed, page),
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


def _genre_drawing(request: Request, tab: str, template: str, build, q: str, user: User, db: Session):
    songs = song_index.all_songs()
    genres = genres_by_folder(db, songs)
    hits = {song.folder for song in search_with_genres(songs, genres, q)} if q.strip() else set()
    drawing = build(songs, genres, get_app_settings(db).genre_map_size, hits)
    return render(request, template, user, **_tab_context(tab, songs, genres, user),
                  q=q, genre="", drawing=drawing, hit_count=len(hits))


@router.get("/genres/map")
def genres_map(
    request: Request,
    q: str = "",
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return _genre_drawing(request, "map", "genres_map.html", genre_map, q, user, db)


@router.get("/genres/connections")
def genres_connections(
    request: Request,
    q: str = "",
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return _genre_drawing(request, "connections", "genres_connections.html", genre_network, q, user, db)


@router.get("/genres/edit")
def genres_edit(
    request: Request,
    q: str = "",
    page: int = 1,
    edited: str = "",
    error: str = "",
    user: User = Depends(require_contributor),
    db: Session = Depends(get_db),
):
    """Every song with its genres to change them - the songs with an open edit only for edited=1."""
    songs = song_index.all_songs()
    genres = genres_by_folder(db, songs)
    file_genres = file_genres_by_folder(db, songs)
    edits = open_edits(db)
    matches = search_with_genres(songs, genres, q, with_genre_only=False)
    if edited:
        matches = [song for song in matches if song.folder in edits]
    known = {genre for names in (*genres.values(), *file_genres.values()) for genre in names}
    return render(
        request, "genres_edit.html", user, **_tab_context("edit", songs, genres, user),
        q=q, genre="", edited=edited, error=error, genres=genres, file_genres=file_genres, edits=edits,
        known_genres=sorted(known, key=str.casefold), result=song_index.paginate(matches, page),
    )


def _edit_answer(request: Request, db: Session, folder: str, q: str, page: int, edited: str, error: str = ""):
    """After a save or reset: JSON for a fetch (the row's genres now, or the
    error), else back to the same search, page and row."""
    if request.headers.get("x-requested-with") == "fetch":
        if error:
            return JSONResponse({"error": error}, status_code=422)
        file_genres = folder_file_genres(db, folder)
        return JSONResponse({"genres": ", ".join(current_genres(db, folder)), "edited": folder in open_edits(db),
                             "file_genres": ", ".join(file_genres)})
    url = f"/genres/edit?q={quote(q, safe='')}&page={page}&edited={quote(edited, safe='')}"
    if error:
        url += f"&error={quote(error, safe='')}"
    return RedirectResponse(f"{url}#{quote(folder, safe='')}", status_code=303)


def _known_folder(folder: str) -> str:
    if song_index.get_by_folder(folder) is None:
        raise HTTPException(status_code=404)
    return folder


@router.post("/genres/edit")
def genres_edit_save(
    request: Request,
    folder: str = Form(""),
    genres: str = Form(""),
    q: str = Form(""),
    page: int = Form(1),
    edited: str = Form(""),
    user: User = Depends(require_contributor),
    db: Session = Depends(get_db),
):
    """Saves a song's genres as a contributor typed them."""
    try:
        save_genre_edit(db, _known_folder(folder), genres, user.username)
    except ValueError as err:
        return _edit_answer(request, db, folder, q, page, edited, str(err))
    return _edit_answer(request, db, folder, q, page, edited)


@router.post("/genres/edit/reset")
def genres_edit_reset(
    request: Request,
    folder: str = Form(""),
    q: str = Form(""),
    page: int = Form(1),
    edited: str = Form(""),
    user: User = Depends(require_contributor),
    db: Session = Depends(get_db),
):
    """Drops a song's edit - back to the genres its files name."""
    reset_genre_edit(db, _known_folder(folder))
    return _edit_answer(request, db, folder, q, page, edited)


@router.get("/genres/edit/export.tsv")
def genres_edit_export(
    user: User = Depends(require_contributor),
    db: Session = Depends(get_db),
):
    """Every open edit for the USDX Song Factory: song file path and genres, tab-separated."""
    return Response(genre_edit_lines(db, Path(settings.songs_dir)),
                     media_type="text/tab-separated-values; charset=utf-8",
                     headers={"Content-Disposition": 'attachment; filename="genre-edits.tsv"'})


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
