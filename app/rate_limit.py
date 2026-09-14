"""About me: a small in-memory brute-force guard for POST /login (see
app/routes/auth.py). Tracks failed attempts per key within a sliding
window and reports whether that key is currently locked out. Keyed by
client IP, not username - locking out an IP only punishes whoever is
guessing passwords from it, whereas a username-keyed lockout would let an
attacker deny a real user access just by repeatedly failing their login
from anywhere.

In-memory only, so this is correct as long as the app runs as a single
process - true today (see Dockerfile: uvicorn with no --workers flag). A
multi-worker or multi-replica deployment would need a shared store (e.g.
Redis) instead, since each process would otherwise track its own count.
"""

from __future__ import annotations

import threading
import time

MAX_ATTEMPTS = 5
WINDOW_SECONDS = 300  # 5 minutes

_lock = threading.Lock()
_failures: dict[str, list[float]] = {}


def _recent(key: str, now: float) -> list[float]:
    cutoff = now - WINDOW_SECONDS
    return [t for t in _failures.get(key, []) if t > cutoff]


def is_locked_out(key: str) -> bool:
    now = time.monotonic()
    with _lock:
        return len(_recent(key, now)) >= MAX_ATTEMPTS


def record_failure(key: str) -> None:
    now = time.monotonic()
    with _lock:
        _failures[key] = [*_recent(key, now), now]


def record_success(key: str) -> None:
    with _lock:
        _failures.pop(key, None)


def reset() -> None:
    """Test-only: clear all tracked state."""
    with _lock:
        _failures.clear()
