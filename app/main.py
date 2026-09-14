"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import __version__
from .config import settings
from .csrf import FORM_FIELD as CSRF_FORM_FIELD
from .csrf import is_valid_csrf_token
from .database import SessionLocal, init_db, wait_for_db
from .deps import AuthRedirect, render
from .routes import admin, auth, reports, requests, songs
from .scheduler import create_scheduler
from .security import seed_admin

_CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}

# Every field this app accepts is short text (the longest realistic value is
# a lyrics/genius URL or a description, a few hundred bytes) - this is
# generous headroom, not a real limit on legitimate use. Rejecting on
# Content-Length means an oversized request is refused before its body is
# ever read into memory, rather than after (the CSRF middleware below would
# otherwise buffer the whole thing via request.body()).
MAX_BODY_BYTES = 256 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.is_dev_secret:
        print("[startup] WARNING: SECRET_KEY is the built-in default - set a strong value in production")
    wait_for_db()
    init_db()
    with SessionLocal() as db:
        seed_admin(db)
    scheduler = create_scheduler()
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title=settings.app_title, version=__version__, lifespan=lifespan)

# Middleware registered with @app.middleware("http")/add_middleware() wraps
# in REVERSE registration order - the last one added ends up outermost, so
# it runs first on the way in and last on the way out. Registration order
# below is therefore, outermost first: SessionMiddleware (added last, at the
# bottom) -> _security_headers -> _body_size_limit -> _csrf_protection
# (added first, innermost). _body_size_limit must run before
# _csrf_protection buffers the body, and _csrf_protection needs
# request.session, which only SessionMiddleware provides.


@app.middleware("http")
async def _csrf_protection(request: Request, call_next):
    """Rejects any non-GET-like request that doesn't carry a valid
    per-session CSRF token as a form field (see app/csrf.py) - centralized
    here so every current and future POST route is covered, rather than
    relying on each route to remember to check.
    """
    if request.method not in _CSRF_SAFE_METHODS:
        # Read body() (not form() directly) first so Starlette caches the
        # raw bytes (see BaseHTTPMiddleware's _CachedRequest) - form()
        # parses via the *stream*, which drains it; without this the
        # route's own Form(...) parameters would see an empty body.
        await request.body()
        form = await request.form()
        submitted = form.get(CSRF_FORM_FIELD)
        if not is_valid_csrf_token(request, submitted):
            return PlainTextResponse(
                "Invalid or missing CSRF token. Please reload the page and try again.",
                status_code=403,
            )
    return await call_next(request)


@app.middleware("http")
async def _body_size_limit(request: Request, call_next):
    """Rejects an oversized request before _csrf_protection (registered
    above, so inner - runs after this) buffers the body into memory.
    Content-Length only - a request without one (chunked transfer) isn't
    covered, an accepted gap for this low-traffic, single-process app.
    """
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > MAX_BODY_BYTES:
        return PlainTextResponse("Request body too large.", status_code=413)
    return await call_next(request)


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    """Applies to every response regardless of route - in particular
    X-Frame-Options protects the login page from clickjacking (a
    transparent iframe overlay tricking a logged-in visitor into an
    unintended click/submit), which a route-specific fix couldn't cover.
    """
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


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
