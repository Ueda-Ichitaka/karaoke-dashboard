"""Password hashing and admin seeding."""

from __future__ import annotations

import bcrypt
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import User

# bcrypt only considers the first 72 bytes of the password.
_BCRYPT_MAX_BYTES = 72


def _prepare(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prepare(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(password), password_hash.encode("utf-8"))
    except ValueError:
        return False


def seed_admin(db: Session) -> None:
    """Create the admin account on first run if ADMIN_PASSWORD is set."""
    if not settings.admin_password:
        print("[startup] ADMIN_PASSWORD not set — skipping admin seed")
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
