"""Report a broken song (login required)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from .. import songs as song_index
from ..broken_categories import CATEGORY_CHOICES
from ..database import get_db
from ..deps import render, require_user
from ..models import BrokenReport, User
from ..validation import broken_report_field_errors

router = APIRouter()


@router.get("/report")
def report_form(request: Request, user: User = Depends(require_user)):
    return render(
        request, "report.html", user,
        errors=[], form={}, submitted=False, category_choices=CATEGORY_CHOICES,
    )


@router.get("/report/songs/partial")
def report_song_picker(
    request: Request,
    q: str = "",
    page: int = 1,
    user: User = Depends(require_user),
):
    result = song_index.search(q, page)
    return render(request, "_song_picker.html", user, q=q, result=result)


@router.post("/report")
def report_submit(
    request: Request,
    song_folder: str = Form(""),
    category: str = Form(""),
    description: str = Form(""),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    song_folder = song_folder.strip()
    category = category.strip().lower()
    description = description.strip()
    errors: list[str] = []

    song = song_index.get_by_folder(song_folder) if song_folder else None
    if not song_folder:
        errors.append("Please pick the song that is broken.")
    elif song is None:
        errors.append("That song is no longer in the library - pick another.")
    errors.extend(broken_report_field_errors(category, description))

    if errors:
        return render(
            request, "report.html", user, status_code=422,
            errors=errors,
            form={"song_folder": song_folder, "category": category, "description": description},
            submitted=False, category_choices=CATEGORY_CHOICES,
        )

    db.add(
        BrokenReport(
            song_folder=song.folder,
            song_artist=song.artist,
            song_title=song.title,
            category=category,
            description=description,
            reporter_id=user.id,
            reporter_username=user.username,
        )
    )
    db.commit()
    return render(
        request, "report.html", user,
        errors=[], form={}, submitted=True, submitted_song=song.display,
        category_choices=CATEGORY_CHOICES,
    )
