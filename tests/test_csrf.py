"""Tests for app/csrf.py: the synchronizer-token CSRF defense used on every
state-changing (POST) request - see app/main.py for the middleware that
enforces it and app/deps.py: render() for how every template gets a token.
"""

from __future__ import annotations

from starlette.requests import Request

from app import csrf


def _fake_request(session: dict) -> Request:
    return Request({"type": "http", "headers": [], "method": "GET", "session": session})


def test_get_csrf_token_creates_one_when_missing():
    session: dict = {}
    token = csrf.get_csrf_token(_fake_request(session))
    assert token
    assert session[csrf.SESSION_KEY] == token


def test_get_csrf_token_is_stable_across_calls():
    session: dict = {}
    request = _fake_request(session)
    first = csrf.get_csrf_token(request)
    second = csrf.get_csrf_token(request)
    assert first == second


def test_is_valid_accepts_the_matching_token():
    session: dict = {}
    request = _fake_request(session)
    token = csrf.get_csrf_token(request)
    assert csrf.is_valid_csrf_token(request, token) is True


def test_is_valid_rejects_a_wrong_token():
    session: dict = {}
    request = _fake_request(session)
    csrf.get_csrf_token(request)
    assert csrf.is_valid_csrf_token(request, "not-the-token") is False


def test_is_valid_rejects_missing_submitted_value():
    session: dict = {}
    request = _fake_request(session)
    csrf.get_csrf_token(request)
    assert csrf.is_valid_csrf_token(request, None) is False
    assert csrf.is_valid_csrf_token(request, "") is False


def test_is_valid_rejects_when_session_has_no_token_yet():
    session: dict = {}
    request = _fake_request(session)
    assert csrf.is_valid_csrf_token(request, "anything") is False


def test_tokens_are_not_predictable():
    session_a: dict = {}
    session_b: dict = {}
    token_a = csrf.get_csrf_token(_fake_request(session_a))
    token_b = csrf.get_csrf_token(_fake_request(session_b))
    assert token_a != token_b
    assert len(token_a) >= 32


# --------------------------------------------------------------- middleware
def test_post_without_a_csrf_token_is_rejected(client):
    r = client.post("/login", data={"username": "admin", "password": "adminadmin"}, include_csrf=False)
    assert r.status_code == 403


def test_post_with_a_wrong_csrf_token_is_rejected(client):
    r = client.post(
        "/login",
        data={"username": "admin", "password": "adminadmin", "csrf_token": "not-the-real-token"},
        include_csrf=False,
    )
    assert r.status_code == 403


def test_post_with_the_real_token_succeeds(client):
    # the client fixture auto-attaches a valid token - this is the control case
    r = client.post(
        "/login", data={"username": "admin", "password": "adminadmin"}, follow_redirects=False
    )
    assert r.status_code == 303


def test_get_requests_are_never_csrf_checked(client):
    assert client.get("/login").status_code == 200


def test_login_form_renders_a_csrf_hidden_field(client):
    r = client.get("/login")
    assert 'name="csrf_token" value="' in r.text


def test_report_form_renders_a_csrf_hidden_field(admin_client):
    r = admin_client.get("/report")
    assert 'name="csrf_token" value="' in r.text
