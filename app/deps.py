"""Shared dependencies: current user, auth guards, template rendering."""

from __future__ import annotations

from fastapi import Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User

templates = Jinja2Templates(directory="app/templates")


class AuthRedirect(Exception):
    """Raised by a guard when the visitor must log in first."""

    def __init__(self, next_url: str) -> None:
        self.next_url = next_url


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        request.session.pop("user_id", None)
        return None
    return user


def _relative_url(request: Request) -> str:
    url = request.url.path
    if request.url.query:
        url += f"?{request.url.query}"
    return url


def require_user(
    request: Request,
    user: User | None = Depends(get_current_user),
) -> User:
    if user is None:
        raise AuthRedirect(next_url=_relative_url(request))
    return user


def require_admin(
    request: Request,
    user: User | None = Depends(get_current_user),
) -> User:
    if user is None:
        raise AuthRedirect(next_url=_relative_url(request))
    if not user.is_admin:
        # Logged in but not allowed - surface a real 403 rather than a login loop.
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def render(
    request: Request,
    name: str,
    user: User | None,
    status_code: int = 200,
    **context: object,
):
    return templates.TemplateResponse(
        request,
        name,
        {
            "app_title": settings.app_title,
            "current_user": user,
            **context,
        },
        status_code=status_code,
    )
