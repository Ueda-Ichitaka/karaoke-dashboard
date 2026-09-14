"""Tests for the request body size cap (app/main.py): rejects an oversized
POST body before it's buffered into memory - defense in depth against
form-parsing DoS (python-multipart CVE-2026-42561/CVE-2026-40347 - fixed by
upgrading the pin, but the app shouldn't rely on the library alone), and
against the CSRF middleware's own request.body() read (it must read the
whole body to populate Starlette's cache) being handed something huge.
"""

from __future__ import annotations

from app.main import MAX_BODY_BYTES


def test_oversized_content_length_is_rejected(client):
    big = "a" * (MAX_BODY_BYTES + 1)
    r = client.post("/login", data={"username": "admin", "password": big}, include_csrf=False)
    assert r.status_code == 413


def test_normal_sized_request_is_unaffected(client):
    r = client.post("/login", data={"username": "admin", "password": "wrong"})
    assert r.status_code == 401
