"""Admin-only views: broken reports, song requests, CSV export, user management."""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import render, require_admin
from ..models import BrokenReport, SongRequest, User
from ..security import hash_password

router = APIRouter(prefix="/admin")

_REPORT_STATES = {"open", "resolved"}
_REQUEST_STATES = {"open", "done"}


@router.get("")
def admin_home():
    return RedirectResponse("/admin/reports", status_code=303)


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
    return render(
        request, "admin/reports.html", user,
        reports=reports, show=show, open_count=open_count or 0,
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
    open_count = db.scalar(select(func.count()).select_from(SongRequest).where(SongRequest.status == "open"))
    return render(
        request, "admin/requests.html", user,
        requests=items, show=show, open_count=open_count or 0,
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
        writer.writerow(["band name", "song name", "youtube link"])
    for r in rows:
        writer.writerow([r.band_name, r.song_name, r.youtube_url or ""])

    filename = "song-requests.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
    if len(password) < 8:
        return RedirectResponse("/admin/users?error=Password+must+be+at+least+8+characters", status_code=303)
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
