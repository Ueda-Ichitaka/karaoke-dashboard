"""Tests for the contributor level (User.is_contributor, app/deps.py:
require_contributor): between a plain user and an admin. A contributor may
use the Reported, Requested and Duplicates pages fully - view, edit, admit,
change status, discard, delete, import and export - and edit genres on the
Genres page; Integrity, Users and Settings stay admin-only. The top nav
shows a contributor the pages they may use, and the Users page sets the
level.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import select

from app.database import SessionLocal
from app.models import SongRequest, User
from app.security import hash_password

CONTRIBUTOR_PAGES = [
    "/admin/reports", "/admin/requests", "/admin/duplicates", "/admin/reports.csv", "/admin/requests.csv",
    "/admin/reports/import", "/admin/requests/import",
]
ADMIN_ONLY_PAGES = ["/admin/integrity", "/admin/users", "/admin/settings"]


def _login(client, username: str, *, contributor: bool = False, admin: bool = False):
    with SessionLocal() as db:
        db.add(User(username=username, password_hash=hash_password("secretsecret"), is_admin=admin,
                    is_contributor=contributor))
        db.commit()
    r = client.post("/login", data={"username": username, "password": "secretsecret"}, follow_redirects=False)
    assert r.status_code == 303
    return client


@pytest.fixture()
def contributor_client(client):
    return _login(client, "helper", contributor=True)


@pytest.fixture()
def user_client(client):
    return _login(client, "singer")


@pytest.mark.parametrize("url", CONTRIBUTOR_PAGES)
def test_a_contributor_may_use_the_contributor_pages(contributor_client, url):
    assert contributor_client.get(url).status_code == 200


@pytest.mark.parametrize("url", ADMIN_ONLY_PAGES)
def test_a_contributor_may_not_use_the_admin_only_pages(contributor_client, url):
    assert contributor_client.get(url).status_code == 403


@pytest.mark.parametrize("url", CONTRIBUTOR_PAGES)
def test_a_plain_user_may_not_use_the_contributor_pages(user_client, url):
    assert user_client.get(url).status_code == 403


def test_a_contributor_may_change_and_delete_requests(contributor_client):
    with SessionLocal() as db:
        db.add(SongRequest(band_name="Journey", song_name="Faithfully", requester_username="helper"))
        db.commit()
        request_id = db.scalar(select(SongRequest.id))
    r = contributor_client.post(f"/admin/requests/{request_id}/status", data={"status": "done"},
                                follow_redirects=False)
    assert r.status_code == 303
    r = contributor_client.post(f"/admin/requests/{request_id}/delete", follow_redirects=False)
    assert r.status_code == 303
    with SessionLocal() as db:
        assert db.get(SongRequest, request_id) is None


def _nav(html: str) -> list[str]:
    nav = html.split('<nav class="tabs">', 1)[1].split("</nav>", 1)[0]
    return re.findall(r">([^<]+)</a>", nav)


def test_the_nav_shows_a_contributor_their_pages(contributor_client):
    html = contributor_client.get("/songs").text
    assert _nav(html) == ["Songs", "What's new", "Genres", "Report broken", "Request song",
                          "Reported", "Requested", "Duplicates"]
    assert '<span class="pill">contributor</span>' in html


def test_the_nav_shows_a_plain_user_no_admin_pages(user_client):
    assert _nav(user_client.get("/songs").text) == ["Songs", "What's new", "Genres", "Report broken",
                                                    "Request song"]


def test_the_nav_shows_an_admin_every_page(admin_client):
    assert _nav(admin_client.get("/songs").text)[5:] == ["Reported", "Requested", "Duplicates", "Integrity",
                                                         "Users", "Settings"]


def _role_cell(html: str, username: str) -> str:
    row = re.search(rf"<strong>{username}</strong>.*?</tr>", html, re.S).group(0)
    return re.findall(r"<td>([^<]*)</td>", row)[0]


def test_the_users_page_creates_a_contributor(admin_client):
    r = admin_client.post("/admin/users", data={"username": "helper", "password": "secretsecret",
                                                "is_contributor": "true"}, follow_redirects=False)
    assert r.status_code == 303
    assert _role_cell(admin_client.get("/admin/users").text, "helper") == "contributor"


def test_the_users_page_toggles_the_contributor_level(admin_client):
    with SessionLocal() as db:
        db.add(User(username="singer", password_hash=hash_password("secretsecret")))
        db.commit()
        user_id = db.scalar(select(User.id).where(User.username == "singer"))
    html = admin_client.get("/admin/users").text
    assert _role_cell(html, "singer") == "user"
    assert "Make contributor" in html
    admin_client.post(f"/admin/users/{user_id}/contributor", follow_redirects=False)
    html = admin_client.get("/admin/users").text
    assert _role_cell(html, "singer") == "contributor"
    assert "Revoke contributor" in html
    admin_client.post(f"/admin/users/{user_id}/contributor", follow_redirects=False)
    assert _role_cell(admin_client.get("/admin/users").text, "singer") == "user"


def test_an_admin_is_shown_as_admin_even_when_also_a_contributor(admin_client):
    with SessionLocal() as db:
        db.add(User(username="boss", password_hash=hash_password("secretsecret"), is_admin=True,
                    is_contributor=True))
        db.commit()
    assert _role_cell(admin_client.get("/admin/users").text, "boss") == "admin"


def test_only_an_admin_may_change_the_contributor_level(contributor_client):
    with SessionLocal() as db:
        user_id = db.scalar(select(User.id).where(User.username == "helper"))
    r = contributor_client.post(f"/admin/users/{user_id}/contributor", follow_redirects=False)
    assert r.status_code == 403
