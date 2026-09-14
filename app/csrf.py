"""About me: CSRF protection for every state-changing (POST) request, using
the synchronizer-token pattern. A random token is generated per session and
must be echoed back as a hidden form field on submit - see app/deps.py:
render() (injects the token into every template as `csrf_token`) and
app/main.py (the middleware that validates it on every POST). Enforced
centrally by that one middleware rather than per-route, so every current
and future POST route is covered without having to remember to opt in.

The token is not rotated on login - it's tied to the session, which is
enough here: reading a visitor's pre-login token to replay it after they
authenticate would require the same access (XSS, or the session cookie
itself) that defeats CSRF protection entirely anyway.
"""

from __future__ import annotations

import hmac
import secrets

from starlette.requests import Request

SESSION_KEY = "csrf_token"
FORM_FIELD = "csrf_token"


def get_csrf_token(request: Request) -> str:
    """The current session's CSRF token, creating one if this is a fresh session."""
    token = request.session.get(SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[SESSION_KEY] = token
    return token


def is_valid_csrf_token(request: Request, submitted: str | None) -> bool:
    expected = request.session.get(SESSION_KEY)
    if not expected or not submitted:
        return False
    return hmac.compare_digest(expected, submitted)
