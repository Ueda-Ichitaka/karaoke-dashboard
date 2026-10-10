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
    exact_section = listing.text.split('id="versions"')[0]
    assert "Coverband - Copycat Song (Reupload)" not in exact_section

    # visiting the dismissed group directly still works (e.g. to double check)
    detail = admin_client.get(f"/admin/duplicates/{group_id}")
    assert detail.status_code == 200
    assert "dismiss" in detail.text.lower()


def test_duplicates_view_shows_rescan_button(admin_client):
    r = admin_client.get("/admin/duplicates")
    assert 'action="/admin/duplicates/rescan"' in r.text
    assert "Rescan" in r.text


def test_duplicates_rescan_redirects_back(admin_client):
    r = admin_client.post("/admin/duplicates/rescan", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/admin/duplicates"


def test_duplicates_rescan_requires_admin(admin_client):
    admin_client.post("/admin/users", data={"username": "hank", "password": "hankhankhank"})
    admin_client.post("/logout")
    admin_client.post("/login", data={"username": "hank", "password": "hankhankhank"}, follow_redirects=False)
    assert admin_client.post("/admin/duplicates/rescan").status_code == 403


def test_non_admin_blocked_from_duplicates(admin_client):
    admin_client.post("/admin/users", data={"username": "carol", "password": "carolcarol"})
    admin_client.post("/logout")
    admin_client.post("/login", data={"username": "carol", "password": "carolcarol"}, follow_redirects=False)

    group_id = _copycat_group_id()
    assert admin_client.get("/admin/duplicates").status_code == 403
    assert admin_client.get(f"/admin/duplicates/{group_id}").status_code == 403
    assert admin_client.post(f"/admin/duplicates/{group_id}/dismiss").status_code == 403


# ------------------------------------- sections: versions, empty folders, ToC
def _section(html: str, section_id: str) -> str:
    return html.split(f'id="{section_id}"', 1)[1].split('<div class="page-head" id=', 1)[0]


def test_duplicates_view_has_three_sections_and_a_toc(admin_client):
    r = admin_client.get("/admin/duplicates")
    for section_id in ("exact", "versions", "empty"):
        assert f'id="{section_id}"' in r.text
        assert f'href="#{section_id}"' in r.text
    assert 'class="toc"' in r.text


def test_versions_section_lists_the_live_version_with_its_siblings(admin_client):
    versions = _section(admin_client.get("/admin/duplicates").text, "versions")
    assert "Coverband - Copycat Song (Live)" in versions
    assert "Coverband - Copycat Song (Reupload)" in versions
    exact = admin_client.get("/admin/duplicates").text.split('id="versions"')[0]
    assert "Coverband - Copycat Song (Live)" not in exact


def test_version_group_can_be_reviewed_and_dismissed(admin_client):
    with SessionLocal() as db:
        group = next(g for g in duplicates.find_version_groups(db) if "copycat song" in g.title_key)
    assert admin_client.get(f"/admin/duplicates/{group.group_id}").status_code == 200
    admin_client.post(f"/admin/duplicates/{group.group_id}/dismiss")
    r = admin_client.get("/admin/duplicates")
    assert "Coverband - Copycat Song (Live)" not in _section(r.text, "versions")
    assert "Coverband - Copycat Song (Reupload)" in r.text.split('id="versions"')[0]  # exact group untouched


def test_empty_section_lists_folders_without_a_song(admin_client):
    empty = _section(admin_client.get("/admin/duplicates").text, "empty")
    assert "Emptyband - Nothing Here" in empty
    assert "Mediaband - Only Audio" in empty
    assert "1 file" in empty
