"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import __version__
from .config import settings
from .database import SessionLocal, init_db, wait_for_db
from .deps import AuthRedirect, render
from .routes import admin, auth, reports, requests, songs
from .security import seed_admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.is_dev_secret:
        print("[startup] WARNING: SECRET_KEY is the built-in default - set a strong value in production")
    wait_for_db()
    init_db()
    with SessionLocal() as db:
        seed_admin(db)
    yield


app = FastAPI(title=settings.app_title, version=__version__, lifespan=lifespan)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="karaoke_session",
    https_only=settings.session_cookie_secure,
    same_site="lax",
    max_age=60 * 60 * 24 * 14,  # 14 days
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(songs.router)
app.include_router(auth.router)
app.include_router(reports.router)
app.include_router(requests.router)
app.include_router(admin.router)


@app.exception_handler(AuthRedirect)
async def _auth_redirect(request: Request, exc: AuthRedirect):
    from urllib.parse import quote

    return RedirectResponse(f"/login?next={quote(exc.next_url, safe='')}", status_code=303)


@app.exception_handler(403)
async def _forbidden(request: Request, exc):
    user_id = request.session.get("user_id")
    user = None
    if user_id:
        with SessionLocal() as db:
            from .models import User

            user = db.get(User, user_id)
    return render(request, "error.html", user, status_code=403,
                  code=403, message="You don't have access to that page.")


@app.exception_handler(404)
async def _not_found(request: Request, exc):
    return render(request, "error.html", None, status_code=404,
                  code=404, message="Page not found.")
