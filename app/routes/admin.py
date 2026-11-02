"""Admin-only views: broken reports, song requests, CSV export, user
management, and settings (including the library-scan utilities)."""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import (
    duplicates,
    format_check,
    import_merge,
    library_history,
    misplaced_check,
    move_export,
    report_import,
    request_import,
    request_matching,
    structure_check,
    upl_export,
)
from .. import songs as song_index
from ..app_logging import configure_logging, get_logger
from ..app_mode import MODE_CHOICES, MODE_CODES
from ..app_settings import get_app_settings
from ..broken_badge import BADGE_MODE_CHOICES, BADGE_MODE_CODES
from ..broken_categories import CATEGORY_CHOICES, CATEGORY_LABELS
from ..config import settings
from ..database import get_db
from ..deps import render, require_admin
from ..duet import DUET_CHOICES, DUET_LABELS
from ..genre_layout import MAX_GENRE_MAP_SIZE
from ..genres import DEFAULT_GENRE, GENRE_CHOICES, format_genres, is_valid_genre, parse_genres
from ..languages import LANGUAGE_CHOICES, LANGUAGE_LABELS
from ..models import BrokenReport, PendingBrokenReport, PendingSongRequest, SongRequest, User
from ..musicbrainz import extract_musicbrainz_id
from ..profiles import PROFILE_CHOICES, PROFILE_CODES, report_category_required_fields
from ..recent_period import MAX_AMOUNT, UNIT_CHOICES, is_valid_unit
from ..scheduler import cron_trigger, reschedule_library_scan
from ..security import MAX_PASSWORD_LENGTH, MAX_USERNAME_LENGTH, hash_password
from ..traits import DEFAULT_TRAIT, TRAIT_CHOICES, format_traits, is_valid_trait, parse_traits
from ..validation import broken_report_field_errors, neutralize_csv_formula, request_field_errors, sanitize_free_text

logger = get_logger(__name__)

router = APIRouter(prefix="/admin")

_REPORT_STATES = {"open", "resolved"}
_REQUEST_STATES = {"open", "done"}

# Fields the admin request edit form (pending and admitted) and the admit
# gate always require - fixed on purpose, independent of the request-form
# profile switch in Settings (app/profiles.py), which governs the public
# form only.
_ADMIN_REQUIRED_FIELDS: frozenset[str] = frozenset({"youtube_url", "language", "musicbrainz_id", "lyrics_url"})

# Fields the admin broken-report edit form (pending and admitted) and its
# admit gate always require on top of the category's own fields
# (app/profiles.py: report_category_required_fields) - independent of the
# report-form profile switch in Settings, same as _ADMIN_REQUIRED_FIELDS.
_ADMIN_REPORT_REQUIRED_FIELDS: frozenset[str] = frozenset({"language", "genius_url"})


def _admin_report_required(category: str) -> set[str]:
    return report_category_required_fields(category) | _ADMIN_REPORT_REQUIRED_FIELDS


def _parse_genre_trait(genre: list[str], trait: list[str]) -> tuple[str, str, list[str]]:
    """Normalizes+validates the admin-only genre/trait fields shared by the
    request and report edit forms (app/genres.py, app/traits.py). Both are
    checkbox groups - a song can carry several of each. Returns the two
    comma-joined strings and any errors.
    """
    errors: list[str] = []

    def _codes(raw_values: list[str], is_valid, label: str) -> list[str]:
        codes: list[str] = []
        for raw in raw_values:
            code = raw.strip().lower()
            if not code:
                continue
            if is_valid(code):
                codes.append(code)
            else:
                errors.append(f"Unrecognized {label}: {code}.")
        return codes

    genre_codes = _codes(genre, is_valid_genre, "genre")
    trait_codes = _codes(trait, is_valid_trait, "trait")
    return format_genres(genre_codes), format_traits(trait_codes), errors


@router.get("")
def admin_home():
    return RedirectResponse("/admin/reports", status_code=303)


# --------------------------------------------------------------------------- settings
# Confirmation shown on the Settings page after a library-scan utility ran.
_LIBRARY_NOTICES = {
    "scanned": "Library scan done.",
    "reset": "Library history reset - every current folder now counts as old.",
}


@router.get("/settings")
def settings_view(
    request: Request,
    library: str = "",
    saved: bool = False,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    app_settings = get_app_settings(db)
    return render(
        request, "admin/settings.html", user,
        errors=[], app_settings=app_settings, profile_choices=PROFILE_CHOICES,
        mode_choices=MODE_CHOICES, badge_mode_choices=BADGE_MODE_CHOICES, unit_choices=UNIT_CHOICES,
        max_amount=MAX_AMOUNT, max_genre_map_size=MAX_GENRE_MAP_SIZE,
        library_notice=_LIBRARY_NOTICES.get(library), saved=saved,
    )


@router.post("/settings")
def settings_update(
    request: Request,
    request_profile: str = Form(""),
    report_profile: str = Form(""),
    mode: str = Form(""),
    logging_enabled: bool = Form(False),
    broken_badge: str | None = Form(None),
    library_scan_cron: str | None = Form(None),
    recent_amount: str | None = Form(None),
    recent_unit: str | None = Form(None),
    genre_map_size: str | None = Form(None),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    app_settings = get_app_settings(db)
    errors: list[str] = []
    if broken_badge is not None and broken_badge not in BADGE_MODE_CODES:
        errors.append("Unrecognized broken-badge mode.")
    if library_scan_cron is not None:
        library_scan_cron = " ".join(library_scan_cron.split())
        try:
            cron_trigger(library_scan_cron)
        except ValueError as err:
            errors.append(f"Invalid library scan schedule: {err}")
    period = None
    if recent_amount is not None or recent_unit is not None:
        amount = (recent_amount or "").strip()
        if not amount.isdigit() or not 1 <= int(amount) <= MAX_AMOUNT or not is_valid_unit(recent_unit or ""):
            errors.append(f"The What's new period must be a whole number from 1 to {MAX_AMOUNT} "
                          "of days, weeks or months.")
        else:
            period = (int(amount), recent_unit)
    map_size = None
    if genre_map_size is not None:
        size = genre_map_size.strip()
        if not size.isdigit() or not 1 <= int(size) <= MAX_GENRE_MAP_SIZE:
            errors.append(f"Genres on the map must be a whole number from 1 to {MAX_GENRE_MAP_SIZE}.")
        else:
            map_size = int(size)
    if request_profile not in PROFILE_CODES:
        errors.append("Unrecognized request-song profile.")
    if report_profile not in PROFILE_CODES:
        errors.append("Unrecognized report-broken profile.")
    if mode not in MODE_CODES:
        errors.append("Unrecognized mode.")
    if errors:
        return render(
            request, "admin/settings.html", user, status_code=422,
            errors=errors, app_settings=app_settings, profile_choices=PROFILE_CHOICES,
            mode_choices=MODE_CHOICES, badge_mode_choices=BADGE_MODE_CHOICES, unit_choices=UNIT_CHOICES,
            max_amount=MAX_AMOUNT, max_genre_map_size=MAX_GENRE_MAP_SIZE,
        )

    app_settings.request_profile = request_profile
    app_settings.report_profile = report_profile
    app_settings.mode = mode
    app_settings.logging_enabled = logging_enabled
    if broken_badge is not None:  # a form without the field keeps the current mode
        app_settings.broken_badge = broken_badge
    if library_scan_cron is not None:  # likewise for the schedule and the period
        app_settings.library_scan_cron = library_scan_cron
    if period is not None:
        app_settings.recent_amount, app_settings.recent_unit = period
    if map_size is not None:
        app_settings.genre_map_size = map_size
    db.commit()
    configure_logging(mode, logging_enabled)
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is not None:
        reschedule_library_scan(scheduler, app_settings.library_scan_cron)
    return RedirectResponse("/admin/settings?saved=1", status_code=303)


@router.post("/settings/library-scan")
def settings_library_scan(user: User = Depends(require_admin)):
    """Runs the library scan behind the songs page's recent panels now."""
    library_history.run_scan()
    return RedirectResponse("/admin/settings?library=scanned", status_code=303)


@router.post("/settings/library-reset")
def settings_library_reset(user: User = Depends(require_admin)):
    """Forgets the recorded library history and scans as a very first scan."""
    library_history.run_reset()
    return RedirectResponse("/admin/settings?library=reset", status_code=303)


# --------------------------------------------------------------------------- reports
@router.get("/reports")
def reports_view(
    request: Request,
    show: str = "open",
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    stmt = select(BrokenReport).order_by(BrokenReport.created_at.desc())
    if show == "open":
        stmt = stmt.where(BrokenReport.status == "open")
    reports = db.scalars(stmt).all()
    open_count = db.scalar(select(func.count()).select_from(BrokenReport).where(BrokenReport.status == "open"))
    pending = db.scalars(select(PendingBrokenReport).order_by(PendingBrokenReport.created_at.asc())).all()
    return render(
        request, "admin/reports.html", user,
        reports=reports, show=show, open_count=open_count or 0, category_labels=CATEGORY_LABELS,
        language_labels=LANGUAGE_LABELS, pending_reports=pending,
        updated_since=library_history.updated_since_report(db, reports),
        pending_updated_since=library_history.updated_since_report(db, pending),
    )


@router.post("/reports/{report_id}/status")
def report_set_status(
    report_id: int,
    status: str = Form(...),
    show: str = Form("open"),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if status not in _REPORT_STATES:
        raise HTTPException(status_code=400, detail="bad status")
    report = db.get(BrokenReport, report_id)
    if report is None:
        raise HTTPException(status_code=404)
    report.status = status
    db.commit()
    return RedirectResponse(f"/admin/reports?show={show}", status_code=303)


@router.get("/reports/{report_id}/edit")
def report_edit_form(
    report_id: int,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    item = db.get(BrokenReport, report_id)
    if item is None:
        raise HTTPException(status_code=404)
    return render(
        request, "admin/report_edit.html", user,
        errors=[], item=item, pending=False, category_choices=CATEGORY_CHOICES, language_choices=LANGUAGE_CHOICES,
        genre_choices=GENRE_CHOICES, trait_choices=TRAIT_CHOICES,
        form={
            "song_folder": item.song_folder, "category": item.category or "",
            "description": item.description or "", "genius_url": item.genius_url or "",
            "language": item.language or "", "cover_url": item.cover_url or "",
            "genre": parse_genres(item.genre), "trait": parse_traits(item.trait),
        },
    )


@router.post("/reports/{report_id}/edit")
def report_edit_submit(
    report_id: int,
    request: Request,
    song_folder: str = Form(""),
    category: str = Form(""),
    description: str = Form(""),
    genius_url: str = Form(""),
    language: str = Form(""),
    cover_url: str = Form(""),
    genre: list[str] = Form([]),
    trait: list[str] = Form([]),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    item = db.get(BrokenReport, report_id)
    if item is None:
        raise HTTPException(status_code=404)

    song_folder = song_folder.strip()
    category = category.strip().lower()
    description = sanitize_free_text(description)
    genius_url = genius_url.strip()
    language = language.strip().lower()
    cover_url = cover_url.strip()
    genre_value, trait_value, genre_trait_errors = _parse_genre_trait(genre, trait)

    errors: list[str] = []
    song = song_index.get_by_folder(song_folder) if song_folder else None
    if not song_folder:
        errors.append("Please pick the song that is broken.")
    elif song is None:
        errors.append("That song is no longer in the library - pick another.")
    errors.extend(broken_report_field_errors(
        category, description, genius_url, language, cover_url, required=_admin_report_required(category),
        allow_file_paths=True,
    ))
    errors.extend(genre_trait_errors)

    if errors:
        return render(
            request, "admin/report_edit.html", user, status_code=422,
            errors=errors, item=item, pending=False, category_choices=CATEGORY_CHOICES,
            language_choices=LANGUAGE_CHOICES, genre_choices=GENRE_CHOICES, trait_choices=TRAIT_CHOICES,
            form={
                "song_folder": song_folder, "category": category, "description": description,
                "genius_url": genius_url, "language": language, "cover_url": cover_url,
                "genre": genre, "trait": trait,
            },
        )

    item.song_folder = song.folder
    item.song_artist = song.artist
    item.song_title = song.title
    item.category = category
    item.description = description
    item.genius_url = genius_url or None
    item.language = language or None
    item.cover_url = cover_url or None
    item.genre = genre_value
    item.trait = trait_value
    db.commit()
    return RedirectResponse("/admin/reports", status_code=303)


# ------------------------------------------------------------- pending reports
@router.get("/reports/pending/{pending_id}/edit")
def pending_report_edit_form(
    pending_id: int,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    item = db.get(PendingBrokenReport, pending_id)
    if item is None:
        raise HTTPException(status_code=404)
    return _render_pending_report_form(request, user, item, errors=[])


def _render_pending_report_form(request: Request, user: User, item: PendingBrokenReport, errors: list[str]):
    """The pending report's edit form filled from its stored values - with
    `errors`, the admit gate's answer (status 422)."""
    return render(
        request, "admin/report_edit.html", user, status_code=422 if errors else 200,
        errors=errors, item=item, pending=True, category_choices=CATEGORY_CHOICES, language_choices=LANGUAGE_CHOICES,
        genre_choices=GENRE_CHOICES, trait_choices=TRAIT_CHOICES,
        form={
            "song_folder": item.song_folder, "category": item.category or "",
            "description": item.description or "", "genius_url": item.genius_url or "",
            "language": item.language or "", "cover_url": item.cover_url or "",
            "genre": parse_genres(item.genre), "trait": parse_traits(item.trait),
        },
    )


@router.post("/reports/pending/{pending_id}/edit")
def pending_report_edit_submit(
    pending_id: int,
    request: Request,
    song_folder: str = Form(""),
    category: str = Form(""),
    description: str = Form(""),
    genius_url: str = Form(""),
    language: str = Form(""),
    cover_url: str = Form(""),
    genre: list[str] = Form([]),
    trait: list[str] = Form([]),
    after_save: str = Form(""),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Saves the pending report; with after_save="admit" (the form's "Save
    and admit" button) it then admits it, or stays on the form with the
    admit gate's errors."""
    item = db.get(PendingBrokenReport, pending_id)
    if item is None:
        raise HTTPException(status_code=404)

    song_folder = song_folder.strip()
    category = category.strip().lower()
    description = sanitize_free_text(description)
    genius_url = genius_url.strip()
    language = language.strip().lower()
    cover_url = cover_url.strip()
    genre_value, trait_value, genre_trait_errors = _parse_genre_trait(genre, trait)

    errors: list[str] = []
    song = song_index.get_by_folder(song_folder) if song_folder else None
    if not song_folder:
        errors.append("Please pick the song that is broken.")
    elif song is None:
        errors.append("That song is no longer in the library - pick another.")
    errors.extend(
        broken_report_field_errors(
            category, description, genius_url, language, cover_url, required=_admin_report_required(category),
            allow_file_paths=True,
        )
    )
    errors.extend(genre_trait_errors)

    if errors:
        return render(
            request, "admin/report_edit.html", user, status_code=422,
            errors=errors, item=item, pending=True, category_choices=CATEGORY_CHOICES,
            language_choices=LANGUAGE_CHOICES, genre_choices=GENRE_CHOICES, trait_choices=TRAIT_CHOICES,
            form={
                "song_folder": song_folder, "category": category, "description": description,
                "genius_url": genius_url, "language": language, "cover_url": cover_url,
                "genre": genre, "trait": trait,
            },
        )

    item.song_folder = song.folder
    item.category = category
    item.description = description
    item.genius_url = genius_url or None
    item.language = language or None
    item.cover_url = cover_url or None
    item.genre = genre_value
    item.trait = trait_value
    db.commit()
    if after_save == "admit":
        admit_errors = _pending_report_admit_errors(item)
        if admit_errors:
            return _render_pending_report_form(request, user, item, admit_errors)
        _admit_pending_report(db, item)
    return RedirectResponse("/admin/reports", status_code=303)


@router.post("/reports/pending/{pending_id}/admit")
def pending_report_admit(
    pending_id: int,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    item = db.get(PendingBrokenReport, pending_id)
    if item is None:
        raise HTTPException(status_code=404)

    errors = _pending_report_admit_errors(item)
    if errors:
        return _render_pending_report_form(request, user, item, errors)
    _admit_pending_report(db, item)
    return RedirectResponse("/admin/reports", status_code=303)


def _pending_report_admit_errors(item: PendingBrokenReport) -> list[str]:
    return broken_report_field_errors(
        item.category or "", item.description, item.genius_url or "", item.language or "",
        item.cover_url or "", required=_admin_report_required(item.category or ""), allow_file_paths=True,
    )


def _admit_pending_report(db: Session, item: PendingBrokenReport, status: str = "open") -> None:
    """Moves a pending report into the admitted list with this status - "open"
    once it passed _pending_report_admit_errors (Admit), "resolved" as it is
    (the Resolved button)."""
    song = song_index.get_by_folder(item.song_folder)
    db.add(
        BrokenReport(
            song_folder=item.song_folder,
            song_artist=song.artist if song else None,
            song_title=song.title if song else None,
            category=item.category,
            description=item.description,
            genius_url=item.genius_url,
            language=item.language,
            cover_url=item.cover_url,
            genre=item.genre,
            trait=item.trait,
            reporter_id=item.reporter_id,
            reporter_username=item.reporter_username,
            created_at=item.created_at,  # when it was drafted, compared with later song-file writes
            status=status,
        )
    )
    logger.info("admitting broken report id=%s %s as %s", item.id, item.song_folder, status)
    db.delete(item)
    db.commit()


@router.post("/reports/pending/{pending_id}/resolve")
def pending_report_resolve(
    pending_id: int,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Closes a report from Needs review in one step: admitted as resolved,
    without Admit's required-field checks."""
    item = db.get(PendingBrokenReport, pending_id)
    if item is None:
        raise HTTPException(status_code=404)
    _admit_pending_report(db, item, status="resolved")
    return RedirectResponse("/admin/reports", status_code=303)


@router.post("/reports/pending/{pending_id}/discard")
def pending_report_discard(
    pending_id: int,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    item = db.get(PendingBrokenReport, pending_id)
    if item is None:
        raise HTTPException(status_code=404)
    logger.info("discarding pending broken report id=%s %s", item.id, item.song_folder)
    db.delete(item)
    db.commit()
    return RedirectResponse("/admin/reports", status_code=303)


@router.get("/reports/import")
def reports_import_form(request: Request, user: User = Depends(require_admin)):
    return render(request, "admin/report_import.html", user, result=None, columns=report_import.COLUMNS)


@router.post("/reports/import")
async def reports_import_submit(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    text = import_merge.decode_csv(await file.read())
    result = report_import.import_reports(db, text, user)
    logger.info(
        "imported broken reports: %s new, %s merged, %s skipped",
        result.imported, result.merged, len(result.skipped),
    )
    return render(request, "admin/report_import.html", user, result=result, columns=report_import.COLUMNS)


@router.get("/reports.csv")
def reports_csv(
    scope: str = "open",
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    stmt = select(BrokenReport).order_by(BrokenReport.created_at.asc())
    if scope == "open":
        stmt = stmt.where(BrokenReport.status == "open")
    rows = db.scalars(stmt).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    if settings.csv_include_header:
        writer.writerow(
            ["band", "song name", "category", "description", "lyrics_url", "language", "cover_url", "genre", "trait"]
        )
    for r in rows:
        writer.writerow(
            [
                r.song_artist or "", r.song_title or "", r.category or "", r.description,
                r.genius_url or "", r.language or "", r.cover_url or "",
                r.genre or DEFAULT_GENRE, r.trait or DEFAULT_TRAIT,
            ]
        )

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="broken.csv"'},
    )


# --------------------------------------------------------------------------- requests
@router.get("/requests")
def requests_view(
    request: Request,
    show: str = "open",
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    stmt = select(SongRequest).order_by(SongRequest.created_at.desc())
    if show == "open":
        stmt = stmt.where(SongRequest.status == "open")
    items = db.scalars(stmt).all()
    for item in items:
        # Not persisted - computed live on every view, like duplicates.py.
        item.library_match = request_matching.find_library_match(item.band_name, item.song_name)
    open_count = db.scalar(select(func.count()).select_from(SongRequest).where(SongRequest.status == "open"))
    pending = db.scalars(select(PendingSongRequest).order_by(PendingSongRequest.created_at.asc())).all()
    return render(
        request, "admin/requests.html", user,
        requests=items, show=show, open_count=open_count or 0, language_labels=LANGUAGE_LABELS,
        duet_labels=DUET_LABELS, pending_requests=pending,
    )


@router.post("/requests/{request_id}/status")
def request_set_status(
    request_id: int,
    status: str = Form(...),
    show: str = Form("open"),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if status not in _REQUEST_STATES:
        raise HTTPException(status_code=400, detail="bad status")
    item = db.get(SongRequest, request_id)
    if item is None:
        raise HTTPException(status_code=404)
    item.status = status
    db.commit()
    return RedirectResponse(f"/admin/requests?show={show}", status_code=303)


@router.post("/requests/{request_id}/delete")
def request_delete(
    request_id: int,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    item = db.get(SongRequest, request_id)
    if item is None:
        raise HTTPException(status_code=404)
    db.delete(item)
    db.commit()
    return RedirectResponse("/admin/requests", status_code=303)


@router.get("/requests/{request_id}/edit")
def request_edit_form(
    request_id: int,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    item = db.get(SongRequest, request_id)
    if item is None:
        raise HTTPException(status_code=404)
    return render(
        request, "admin/request_edit.html", user,
        errors=[], item=item, pending=False, language_choices=LANGUAGE_CHOICES, duet_choices=DUET_CHOICES,
        genre_choices=GENRE_CHOICES, trait_choices=TRAIT_CHOICES,
        form={
            "band_name": item.band_name, "song_name": item.song_name,
            "youtube_url": item.youtube_url or "", "language": item.language or "",
            "musicbrainz_id": item.musicbrainz_id or "", "lyrics_url": item.lyrics_url or "",
            "cover_url": item.cover_url or "", "duet": item.duet or "",
            "genre": parse_genres(item.genre), "trait": parse_traits(item.trait),
        },
    )


@router.post("/requests/{request_id}/edit")
def request_edit_submit(
    request_id: int,
    request: Request,
    band_name: str = Form(""),
    song_name: str = Form(""),
    youtube_url: str = Form(""),
    language: str = Form(""),
    musicbrainz_id: str = Form(""),
    lyrics_url: str = Form(""),
    cover_url: str = Form(""),
    duet: str = Form(""),
    genre: list[str] = Form([]),
    trait: list[str] = Form([]),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    item = db.get(SongRequest, request_id)
    if item is None:
        raise HTTPException(status_code=404)

    band_name = band_name.strip()
    song_name = song_name.strip()
    youtube_url = youtube_url.strip()
    language = language.strip().lower()
    musicbrainz_id = extract_musicbrainz_id(musicbrainz_id)
    lyrics_url = lyrics_url.strip()
    cover_url = cover_url.strip()
    duet = duet.strip().lower()
    genre_value, trait_value, genre_trait_errors = _parse_genre_trait(genre, trait)

    errors = request_field_errors(
        band_name, song_name, youtube_url, language, musicbrainz_id, cover_url, duet,
        lyrics_url=lyrics_url, required=_ADMIN_REQUIRED_FIELDS, allow_file_paths=True,
    )
    errors.extend(genre_trait_errors)
    if errors:
        return render(
            request, "admin/request_edit.html", user, status_code=422,
            errors=errors, item=item, pending=False, language_choices=LANGUAGE_CHOICES, duet_choices=DUET_CHOICES,
            genre_choices=GENRE_CHOICES, trait_choices=TRAIT_CHOICES,
            form={
                "band_name": band_name, "song_name": song_name, "youtube_url": youtube_url,
                "language": language, "musicbrainz_id": musicbrainz_id, "lyrics_url": lyrics_url,
                "cover_url": cover_url, "duet": duet, "genre": genre, "trait": trait,
            },
        )

    item.band_name = band_name
    item.song_name = song_name
    item.youtube_url = youtube_url or None
    item.language = language or None
    item.musicbrainz_id = musicbrainz_id or None
    item.lyrics_url = lyrics_url or None
    item.cover_url = cover_url or None
    item.duet = duet or None
    item.genre = genre_value
    item.trait = trait_value
    db.commit()
    return RedirectResponse("/admin/requests", status_code=303)


# ------------------------------------------------------------ pending requests
@router.get("/requests/pending/{pending_id}/edit")
def pending_request_edit_form(
    pending_id: int,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    item = db.get(PendingSongRequest, pending_id)
    if item is None:
        raise HTTPException(status_code=404)
    return _render_pending_request_form(request, user, item, errors=[])


def _render_pending_request_form(request: Request, user: User, item: PendingSongRequest, errors: list[str]):
    """The pending request's edit form filled from its stored values - with
    `errors`, the admit gate's answer (status 422)."""
    return render(
        request, "admin/request_edit.html", user, status_code=422 if errors else 200,
        errors=errors, item=item, pending=True, language_choices=LANGUAGE_CHOICES, duet_choices=DUET_CHOICES,
        genre_choices=GENRE_CHOICES, trait_choices=TRAIT_CHOICES,
        form={
            "band_name": item.band_name, "song_name": item.song_name,
            "youtube_url": item.youtube_url or "", "language": item.language or "",
            "musicbrainz_id": item.musicbrainz_id or "", "lyrics_url": item.lyrics_url or "",
            "cover_url": item.cover_url or "", "duet": item.duet or "",
            "genre": parse_genres(item.genre), "trait": parse_traits(item.trait),
        },
    )


@router.post("/requests/pending/{pending_id}/edit")
def pending_request_edit_submit(
    pending_id: int,
    request: Request,
    band_name: str = Form(""),
    song_name: str = Form(""),
    youtube_url: str = Form(""),
    language: str = Form(""),
    musicbrainz_id: str = Form(""),
    lyrics_url: str = Form(""),
    cover_url: str = Form(""),
    duet: str = Form(""),
    genre: list[str] = Form([]),
    trait: list[str] = Form([]),
    after_save: str = Form(""),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Saves the pending request; with after_save="admit" (the form's "Save
    and admit" button) it then admits it, or stays on the form with the
    admit gate's errors."""
    item = db.get(PendingSongRequest, pending_id)
    if item is None:
        raise HTTPException(status_code=404)

    band_name = band_name.strip()
    song_name = song_name.strip()
    youtube_url = youtube_url.strip()
    language = language.strip().lower()
    musicbrainz_id = extract_musicbrainz_id(musicbrainz_id)
    lyrics_url = lyrics_url.strip()
    cover_url = cover_url.strip()
    duet = duet.strip().lower()
    genre_value, trait_value, genre_trait_errors = _parse_genre_trait(genre, trait)

    errors = request_field_errors(
        band_name, song_name, youtube_url, language, musicbrainz_id, cover_url, duet,
        lyrics_url=lyrics_url, required=_ADMIN_REQUIRED_FIELDS, allow_file_paths=True,
    )
    errors.extend(genre_trait_errors)
    if errors:
        return render(
            request, "admin/request_edit.html", user, status_code=422,
            errors=errors, item=item, pending=True, language_choices=LANGUAGE_CHOICES, duet_choices=DUET_CHOICES,
            genre_choices=GENRE_CHOICES, trait_choices=TRAIT_CHOICES,
            form={
                "band_name": band_name, "song_name": song_name, "youtube_url": youtube_url,
                "language": language, "musicbrainz_id": musicbrainz_id, "lyrics_url": lyrics_url,
                "cover_url": cover_url, "duet": duet, "genre": genre, "trait": trait,
            },
        )

    item.band_name = band_name
    item.song_name = song_name
    item.youtube_url = youtube_url or None
    item.language = language or None
    item.musicbrainz_id = musicbrainz_id or None
    item.lyrics_url = lyrics_url or None
    item.cover_url = cover_url or None
    item.duet = duet or None
    item.genre = genre_value
    item.trait = trait_value
    db.commit()
    if after_save == "admit":
        admit_errors = _pending_request_admit_errors(db, item)
        if admit_errors:
            return _render_pending_request_form(request, user, item, admit_errors)
        _admit_pending_request(db, item)
    return RedirectResponse("/admin/requests", status_code=303)


@router.post("/requests/pending/{pending_id}/admit")
def pending_request_admit(
    pending_id: int,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    item = db.get(PendingSongRequest, pending_id)
    if item is None:
        raise HTTPException(status_code=404)

    errors = _pending_request_admit_errors(db, item)
    if errors:
        return _render_pending_request_form(request, user, item, errors)
    _admit_pending_request(db, item)
    return RedirectResponse("/admin/requests", status_code=303)


def _pending_request_admit_errors(db: Session, item: PendingSongRequest) -> list[str]:
    errors = request_field_errors(
        item.band_name, item.song_name, item.youtube_url or "", item.language or "",
        item.musicbrainz_id or "", item.cover_url or "", item.duet or "",
        lyrics_url=item.lyrics_url or "", required=_ADMIN_REQUIRED_FIELDS, allow_file_paths=True,
    )
    app_settings = get_app_settings(db)
    library_match = request_matching.find_library_match(item.band_name, item.song_name)
    if library_match and library_match.exact_folder and app_settings.mode != "debug":
        errors.append(
            f'"{item.band_name} - {item.song_name}" is already in the library '
            f'(folder: "{library_match.folder}") - switch to debug mode to admit it anyway.'
        )
    return errors


def _admit_pending_request(db: Session, item: PendingSongRequest) -> None:
    """Moves a pending request that passed _pending_request_admit_errors
    into the exportable list."""
    db.add(
        SongRequest(
            band_name=item.band_name,
            song_name=item.song_name,
            youtube_url=item.youtube_url,
            language=item.language,
            musicbrainz_id=item.musicbrainz_id,
            lyrics_url=item.lyrics_url,
            cover_url=item.cover_url,
            duet=item.duet,
            genre=item.genre,
            trait=item.trait,
            requester_id=item.requester_id,
            requester_username=item.requester_username,
        )
    )
    logger.info("admitting song request id=%s %s - %s", item.id, item.band_name, item.song_name)
    db.delete(item)
    db.commit()


@router.post("/requests/pending/{pending_id}/discard")
def pending_request_discard(
    pending_id: int,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    item = db.get(PendingSongRequest, pending_id)
    if item is None:
        raise HTTPException(status_code=404)
    logger.info("discarding pending song request id=%s %s - %s", item.id, item.band_name, item.song_name)
    db.delete(item)
    db.commit()
    return RedirectResponse("/admin/requests", status_code=303)


@router.get("/requests/import")
def requests_import_form(request: Request, user: User = Depends(require_admin)):
    return render(request, "admin/request_import.html", user, result=None, columns=request_import.COLUMNS)


@router.post("/requests/import")
async def requests_import_submit(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    text = import_merge.decode_csv(await file.read())
    result = request_import.import_requests(db, text, user)
    logger.info(
        "imported song requests: %s new, %s merged, %s skipped",
        result.imported, result.merged, len(result.skipped),
    )
    return render(request, "admin/request_import.html", user, result=result, columns=request_import.COLUMNS)


@router.get("/requests.csv")
def requests_csv(
    scope: str = "open",
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    stmt = select(SongRequest).order_by(SongRequest.created_at.asc())
    if scope == "open":
        stmt = stmt.where(SongRequest.status == "open")
    rows = db.scalars(stmt).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    if settings.csv_include_header:
        writer.writerow(
            [
                "band name", "song name", "youtube link", "language", "musicbrainz_id",
                "lyrics_url", "cover_url", "duet", "genre", "trait",
            ]
        )
    for r in rows:
        writer.writerow(
            [
                neutralize_csv_formula(r.band_name), neutralize_csv_formula(r.song_name),
                r.youtube_url or "", r.language or "",
                neutralize_csv_formula(r.musicbrainz_id or ""), r.lyrics_url or "",
                r.cover_url or "", r.duet or "", r.genre or DEFAULT_GENRE, r.trait or DEFAULT_TRAIT,
            ]
        )

    filename = "song-requests.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --------------------------------------------------------------------------- duplicates
@router.get("/duplicates")
def duplicates_view(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return render(
        request, "admin/duplicates.html", user,
        groups=duplicates.find_duplicate_groups(db),
        version_groups=duplicates.find_version_groups(db),
        empty_folders=duplicates.find_empty_folders(),
        last_scanned_at=duplicates.last_scanned_at(),
    )


@router.post("/duplicates/rescan")
def duplicates_rescan(user: User = Depends(require_admin)):
    duplicates.refresh_cache()
    return RedirectResponse("/admin/duplicates", status_code=303)


@router.get("/duplicates/{group_id}")
def duplicate_detail(
    group_id: str,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    group = duplicates.get_duplicate_group(db, group_id)
    if group is None:
        raise HTTPException(status_code=404)
    return render(
        request, "admin/duplicate_detail.html", user,
        group=group,
        rows=duplicates.field_diff(group),
        dismissed=duplicates.is_dismissed(db, group),
    )


@router.post("/duplicates/{group_id}/dismiss")
def duplicate_dismiss(
    group_id: str,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    group = duplicates.get_duplicate_group(db, group_id)
    if group is None:
        raise HTTPException(status_code=404)
    duplicates.dismiss_group(db, group, dismissed_by=user.username)
    return RedirectResponse("/admin/duplicates#versions" if group.is_version else "/admin/duplicates", status_code=303)


# --------------------------------------------------------------------------- users
@router.get("/users")
def users_view(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
    error: str | None = None,
    created: str | None = None,
):
    users = db.scalars(select(User).order_by(User.username)).all()
    return render(request, "admin/users.html", user, users=users, error=error, created=created)


@router.post("/users")
def users_create(
    username: str = Form(""),
    password: str = Form(""),
    is_admin: bool = Form(False),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    username = username.strip()
    if not username or not password:
        return RedirectResponse("/admin/users?error=Username+and+password+are+required", status_code=303)
    if len(username) > MAX_USERNAME_LENGTH:
        return RedirectResponse("/admin/users?error=Username+is+too+long", status_code=303)
    if len(password) < 8:
        return RedirectResponse("/admin/users?error=Password+must+be+at+least+8+characters", status_code=303)
    if len(password) > MAX_PASSWORD_LENGTH:
        return RedirectResponse("/admin/users?error=Password+is+too+long", status_code=303)
    if db.scalar(select(User).where(User.username == username)):
        return RedirectResponse("/admin/users?error=That+username+already+exists", status_code=303)
    db.add(
        User(
            username=username,
            password_hash=hash_password(password),
            is_admin=bool(is_admin),
            is_active=True,
        )
    )
    db.commit()
    return RedirectResponse(f"/admin/users?created={username}", status_code=303)


@router.post("/users/{user_id}/password")
def users_reset_password(
    user_id: int,
    password: str = Form(""),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if len(password) < 8:
        return RedirectResponse("/admin/users?error=Password+must+be+at+least+8+characters", status_code=303)
    if len(password) > MAX_PASSWORD_LENGTH:
        return RedirectResponse("/admin/users?error=Password+is+too+long", status_code=303)
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404)
    target.password_hash = hash_password(password)
    db.commit()
    return RedirectResponse("/admin/users?created=" + target.username, status_code=303)


@router.post("/users/{user_id}/admin")
def users_toggle_admin(
    user_id: int,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404)
    if target.id == user.id:
        return RedirectResponse("/admin/users?error=You+cannot+change+your+own+admin+flag", status_code=303)
    target.is_admin = not target.is_admin
    db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/active")
def users_toggle_active(
    user_id: int,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404)
    if target.id == user.id:
        return RedirectResponse("/admin/users?error=You+cannot+disable+your+own+account", status_code=303)
    target.is_active = not target.is_active
    db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/delete")
def users_delete(
    user_id: int,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404)
    if target.id == user.id:
        return RedirectResponse("/admin/users?error=You+cannot+delete+your+own+account", status_code=303)
    db.delete(target)
    db.commit()
    return RedirectResponse("/admin/users", status_code=303)


# ------------------------------------------------------------------ integrity
@router.get("/integrity")
def integrity_view(
    request: Request,
    issue: str = "",
    user: User = Depends(require_admin),
):
    structure_issues = structure_check.check_structure()
    trees = {s.folder: structure_check.folder_tree(s.folder) for s in structure_issues}
    all_format_reports = format_check.check_library()
    return render(
        request, "admin/integrity.html", user,
        format_reports=format_check.filter_reports(all_format_reports, issue),
        format_total=len(all_format_reports),
        format_kinds=format_check.issue_kind_counts(all_format_reports),
        format_issue=issue,
        structure_issues=structure_issues,
        trees=trees,
        misplaced_songs=misplaced_check.find_misplaced_songs(),
    )


@router.get("/integrity/format-issues.upl")
def integrity_format_issues_upl_export(user: User = Depends(require_admin)):
    content = upl_export.build_format_issues_upl(format_check.check_library())
    return StreamingResponse(
        iter([content]),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="format-issues.upl"'},
    )


@router.get("/integrity/non-conforming.moves")
def integrity_structure_moves_export(user: User = Depends(require_admin)):
    content = move_export.build_structure_moves(structure_check.check_structure())
    return StreamingResponse(
        iter([content]),
        media_type="application/octet-stream",
        headers={"Content-Disposition": 'attachment; filename="non-conforming.moves"'},
    )


@router.get("/integrity/misplaced.moves")
def integrity_misplaced_moves_export(user: User = Depends(require_admin)):
    content = move_export.build_misplaced_moves(misplaced_check.find_misplaced_songs())
    return StreamingResponse(
        iter([content]),
        media_type="application/octet-stream",
        headers={"Content-Disposition": 'attachment; filename="misplaced.moves"'},
    )
