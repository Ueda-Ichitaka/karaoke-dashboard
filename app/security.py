"""Password hashing, timing-safe login verification, and admin seeding."""

from __future__ import annotations

import bcrypt
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import User

# bcrypt only considers the first 72 bytes of the password.
_BCRYPT_MAX_BYTES = 72

# Generous ceilings, well above any real username/password, used at every
# entry point that accepts one (login, admin user creation/password reset).
# Username in particular must fit the users.username column (VARCHAR(64)) -
# an oversized value hitting Postgres uncaught would 500 instead of cleanly
# failing (the same overflow-crash class fixed for musicbrainz_id).
MAX_USERNAME_LENGTH = 64
MAX_PASSWORD_LENGTH = 512


def _prepare(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prepare(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(password), password_hash.encode("utf-8"))
    except ValueError:
        return False


# A fixed, valid bcrypt hash with no real account behind it. verify_login()
# compares against this when the user doesn't exist (or is inactive) so a
# "no such user" failure costs the same bcrypt computation as a "wrong
# password" one - otherwise the missing hashing step makes a nonexistent
# username measurably faster to reject, a timing side-channel an attacker
# can use to enumerate valid usernames without ever seeing an error message
# that says so.
_DUMMY_HASH = hash_password("not-a-real-password-used-only-to-equalize-timing")


def verify_login(password: str, user: User | None) -> bool:
    password_hash = user.password_hash if user is not None and user.is_active else _DUMMY_HASH
    password_ok = verify_password(password, password_hash)
    return password_ok and user is not None and user.is_active


def seed_admin(db: Session) -> None:
    """Create the admin account on first run if ADMIN_PASSWORD is set."""
    if not settings.admin_password:
        print("[startup] ADMIN_PASSWORD not set - skipping admin seed")
        return

    existing = db.scalar(select(User).where(User.username == settings.admin_username))
    if existing:
        return

    db.add(
        User(
            username=settings.admin_username,
            password_hash=hash_password(settings.admin_password),
            is_admin=True,
            is_active=True,
        )
    )
    db.commit()
    print(f"[startup] seeded admin user '{settings.admin_username}'")
