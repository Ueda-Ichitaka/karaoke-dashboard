"""Login / logout."""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, render
from ..models import User
from ..security import verify_password

router = APIRouter()


def _safe_next(raw: str | None) -> str:
    """Only allow same-site relative redirects."""
    if not raw:
        return "/songs"
    parsed = urlparse(raw)
    if parsed.scheme or parsed.netloc:
        return "/songs"
    path = parsed.path or "/songs"
    if not path.startswith("/"):
        return "/songs"
    return path + (f"?{parsed.query}" if parsed.query else "")


@router.get("/login")
def login_form(request: Request, next: str | None = None, user: User | None = Depends(get_current_user)):
    if user is not None:
        return RedirectResponse(_safe_next(next), status_code=303)
    return render(request, "login.html", user, next=_safe_next(next), error=None)


@router.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str | None = Form(None),
    db: Session = Depends(get_db),
):
    target = _safe_next(next)
    user = db.scalar(select(User).where(User.username == username.strip()))
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        return render(
            request, "login.html", None, status_code=401,
            next=target, error="Invalid username or password.",
        )
    request.session["user_id"] = user.id
    return RedirectResponse(target, status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
