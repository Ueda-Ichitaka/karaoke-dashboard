"""Login / logout."""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import rate_limit
from ..database import get_db
from ..deps import get_current_user, render
from ..models import User
from ..security import MAX_PASSWORD_LENGTH, MAX_USERNAME_LENGTH, verify_login

router = APIRouter()


def _safe_next(raw: str | None) -> str:
    """Only allow same-site relative redirects.

    A leading backslash is normalized to a forward slash first: browsers
    treat "\\" the same as "/" when resolving a URL (WHATWG URL spec, for
    "special" schemes like http/https), so "/\\evil.example.com" would
    otherwise slip past the scheme/netloc check below and be resolved as
    "//evil.example.com" - a protocol-relative redirect off-site.
    """
    if not raw:
        return "/songs"
    normalized = raw.replace("\\", "/")
    parsed = urlparse(normalized)
    if parsed.scheme or parsed.netloc:
        return "/songs"
    path = parsed.path or "/songs"
    if not path.startswith("/"):
        return "/songs"
    return path + (f"?{parsed.query}" if parsed.query else "")


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


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
    client_ip = _client_ip(request)

    if rate_limit.is_locked_out(client_ip):
        return render(
            request, "login.html", None, status_code=429,
            next=target, error="Too many failed login attempts. Please wait a few minutes and try again.",
        )

    if len(username) > MAX_USERNAME_LENGTH or len(password) > MAX_PASSWORD_LENGTH:
        rate_limit.record_failure(client_ip)
        return render(
            request, "login.html", None, status_code=401,
            next=target, error="Invalid username or password.",
        )

    user = db.scalar(select(User).where(User.username == username.strip()))
    if not verify_login(password, user):
        rate_limit.record_failure(client_ip)
        return render(
            request, "login.html", None, status_code=401,
            next=target, error="Invalid username or password.",
        )

    rate_limit.record_success(client_ip)
    request.session["user_id"] = user.id
    return RedirectResponse(target, status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
