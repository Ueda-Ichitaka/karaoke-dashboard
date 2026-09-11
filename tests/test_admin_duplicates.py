"""Route-level tests for the admin duplicate-songs review page."""

from __future__ import annotations

from app import duplicates
from app.database import SessionLocal


def _copycat_group_id() -> str:
    with SessionLocal() as db:
        group = next(g for g in duplicates.find_duplicate_groups(db) if g.title_key == "copycat song")
        return group.group_id


def test_duplicates_list_shows_group_and_both_paths(admin_client):
    r = admin_client.get("/admin/duplicates")
    assert r.status_code == 200
    assert "Copycat Song" in r.text
    assert "Coverband - Copycat Song" in r.text
    assert "Coverband - Copycat Song (Reupload)" in r.text
    # the lone duet copy has no dupe and must not show up
    assert "Coverband - Copycat Song (Duet)" not in r.text


def test_duplicate_detail_shows_diff_and_dismiss_form(admin_client):
    group_id = _copycat_group_id()
    r = admin_client.get(f"/admin/duplicates/{group_id}")
    assert r.status_code == 200
    assert "Genre" in r.text
    assert "Rock" in r.text and "Pop" in r.text
    assert "Coverband - Copycat Song" in r.text
    assert f"/admin/duplicates/{group_id}/dismiss" in r.text


def test_unknown_group_id_is_404(admin_client):
    assert admin_client.get("/admin/duplicates/deadbeefdeadbeef").status_code == 404


def test_dismiss_removes_group_from_list_and_persists(admin_client):
    group_id = _copycat_group_id()
    r = admin_client.post(f"/admin/duplicates/{group_id}/dismiss", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/admin/duplicates"

    listing = admin_client.get("/admin/duplicates")
    assert "Coverband - Copycat Song (Reupload)" not in listing.text

    # visiting the dismissed group directly still works (e.g. to double check)
    detail = admin_client.get(f"/admin/duplicates/{group_id}")
    assert detail.status_code == 200
    assert "dismiss" in detail.text.lower()


def test_non_admin_blocked_from_duplicates(admin_client):
    admin_client.post("/admin/users", data={"username": "carol", "password": "carolcarol"})
    admin_client.post("/logout")
    admin_client.post("/login", data={"username": "carol", "password": "carolcarol"}, follow_redirects=False)

    group_id = _copycat_group_id()
    assert admin_client.get("/admin/duplicates").status_code == 403
    assert admin_client.get(f"/admin/duplicates/{group_id}").status_code == 403
    assert admin_client.post(f"/admin/duplicates/{group_id}/dismiss").status_code == 403
