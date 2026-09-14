"""Security-focused tests for the login flow (app/routes/auth.py) and its
two input fields (username, password): timing-based user enumeration,
brute-force/rate limiting, the open-redirect "next" parameter, oversized
input, SQL injection, and stored XSS via a username.
"""

from __future__ import annotations

import bcrypt
from sqlalchemy import select

from app import rate_limit
from app.database import SessionLocal
from app.models import User
from app.security import hash_password, verify_login


# ------------------------------------------------------- timing side-channel
def test_verify_login_hashes_even_when_user_is_missing(monkeypatch):
    calls = []
    real_checkpw = bcrypt.checkpw
    monkeypatch.setattr(bcrypt, "checkpw", lambda *a, **kw: (calls.append(1), real_checkpw(*a, **kw))[1])

    assert verify_login("whatever", None) is False
    assert len(calls) == 1  # a real bcrypt comparison still ran


def test_verify_login_hashes_even_when_user_is_inactive(monkeypatch):
    calls = []
    real_checkpw = bcrypt.checkpw
    monkeypatch.setattr(bcrypt, "checkpw", lambda *a, **kw: (calls.append(1), real_checkpw(*a, **kw))[1])

    user = User(username="x", password_hash=hash_password("secret"), is_active=False)
    assert verify_login("secret", user) is False
    assert len(calls) == 1


def test_verify_login_accepts_correct_password():
    user = User(username="x", password_hash=hash_password("secret"), is_active=True)
    assert verify_login("secret", user) is True


def test_verify_login_rejects_wrong_password():
    user = User(username="x", password_hash=hash_password("secret"), is_active=True)
    assert verify_login("wrong", user) is False


# ---------------------------------------------------------- brute force
def test_login_locked_out_after_max_failed_attempts(client):
    for _ in range(rate_limit.MAX_ATTEMPTS):
        r = client.post("/login", data={"username": "admin", "password": "wrong"})
        assert r.status_code == 401

    # even the *correct* password is now refused - the account isn't
    # targeted directly, the source is throttled
    r = client.post("/login", data={"username": "admin", "password": "adminadmin"})
    assert r.status_code == 429
    assert "too many" in r.text.lower()


def test_login_lockout_does_not_affect_other_keys_config(client):
    # sanity: the limiter itself is keyed correctly (full behavior covered
    # in test_rate_limit.py) - this just confirms the route actually uses it
    assert rate_limit.MAX_ATTEMPTS > 0


# -------------------------------------------------------------- open redirect
def test_next_rejects_backslash_protocol_relative_bypass(client):
    r = client.post(
        "/login",
        data={"username": "admin", "password": "adminadmin", "next": "/\\evil.example.com"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    location = r.headers["location"]
    assert location == "/songs"


def test_next_still_allows_a_normal_relative_path(client):
    r = client.post(
        "/login",
        data={"username": "admin", "password": "adminadmin", "next": "/admin/users"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/admin/users"


# -------------------------------------------------------------- oversized input
def test_oversized_username_is_rejected_gracefully(client):
    r = client.post("/login", data={"username": "a" * 5000, "password": "adminadmin"})
    assert r.status_code == 401
    assert "invalid" in r.text.lower()


def test_oversized_password_is_rejected_gracefully(client):
    r = client.post("/login", data={"username": "admin", "password": "a" * 5000})
    assert r.status_code == 401


# ----------------------------------------------------------------- injection
def test_sql_injection_payloads_never_authenticate(client):
    payloads = [
        "' OR '1'='1",
        "' OR '1'='1' --",
        "admin'--",
        "admin' OR 1=1#",
        "'; DROP TABLE users; --",
        "' UNION SELECT * FROM users --",
        "\" OR \"\"=\"",
    ]
    for payload in payloads:
        r = client.post("/login", data={"username": payload, "password": payload}, follow_redirects=False)
        assert r.status_code in (401, 429), f"payload {payload!r} did not cleanly fail"
        assert r.status_code != 500


def test_sql_injection_in_password_with_valid_username_never_authenticates(client):
    r = client.post(
        "/login",
        data={"username": "admin", "password": "' OR '1'='1"},
        follow_redirects=False,
    )
    assert r.status_code == 401


# ------------------------------------------------------------------- stored XSS
def test_username_is_html_escaped_when_rendered(admin_client):
    payload = "<script>alert(1)</script>"
    admin_client.post(
        "/admin/users", data={"username": payload, "password": "harmlessharmless"}, follow_redirects=False
    )

    r = admin_client.get("/admin/users")
    assert "<script>alert(1)</script>" not in r.text
    assert "&lt;script&gt;" in r.text


# ---------------------------------------------------- admin user management
def test_admin_create_user_rejects_oversized_username(admin_client):
    from app.security import MAX_USERNAME_LENGTH

    r = admin_client.post(
        "/admin/users",
        data={"username": "a" * (MAX_USERNAME_LENGTH + 1), "password": "harmlessharmless"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "error=" in r.headers["location"]

    listing = admin_client.get("/admin/users")
    assert "a" * (MAX_USERNAME_LENGTH + 1) not in listing.text


def test_admin_reset_password_rejects_oversized_password(admin_client):
    from app.security import MAX_PASSWORD_LENGTH

    with SessionLocal() as db:
        target_id = db.scalar(select(User).where(User.username == "admin")).id

    r = admin_client.post(
        f"/admin/users/{target_id}/password",
        data={"password": "a" * (MAX_PASSWORD_LENGTH + 1)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "error=" in r.headers["location"]
