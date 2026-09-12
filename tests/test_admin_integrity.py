"""Route-level tests for the admin integrity/structure-check view."""

from __future__ import annotations


def test_integrity_view_shows_structure_issues(admin_client):
    r = admin_client.get("/admin/integrity")
    assert r.status_code == 200
    # non-conforming name (see conftest.py)
    assert "PlainFolderNoSeparator" in r.text
    # nested subfolder (see conftest.py)
    assert "Coverband - Import Batch" in r.text
    assert "CD1" in r.text


def test_integrity_view_shows_format_issues(admin_client):
    r = admin_client.get("/admin/integrity")
    assert r.status_code == 200
    # "Testband - Multi Song" folders have no #MP3/#AUDIO reference at all
    assert "Multi Song" in r.text or "SongA.txt" in r.text
    # a stray non-UltraStar readme.txt must not show up as a format issue
    assert "readme.txt" not in r.text


def test_non_admin_blocked_from_integrity(admin_client):
    admin_client.post("/admin/users", data={"username": "dana", "password": "danadanadana"})
    admin_client.post("/logout")
    admin_client.post("/login", data={"username": "dana", "password": "danadanadana"}, follow_redirects=False)
    assert admin_client.get("/admin/integrity").status_code == 403


def test_integrity_requires_login(client):
    r = client.get("/admin/integrity", follow_redirects=False)
    assert r.status_code == 303


def test_integrity_view_links_to_upl_export(admin_client):
    r = admin_client.get("/admin/integrity")
    assert "/admin/integrity/non-conforming.upl" in r.text


def test_upl_export_downloads_playlist(admin_client):
    r = admin_client.get("/admin/integrity/non-conforming.upl")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    assert r.headers["content-type"].startswith("text/plain")
    body = r.text
    assert "#Ultrastar Deluxe Playlist Format v1.0" in body
    # "Coverband - Import Batch" / CD1 / Track.txt from conftest.py
    assert "Coverband : Track" in body


def test_upl_export_requires_admin(admin_client):
    admin_client.post("/admin/users", data={"username": "erin", "password": "erinerinerin"})
    admin_client.post("/logout")
    admin_client.post("/login", data={"username": "erin", "password": "erinerinerin"}, follow_redirects=False)
    assert admin_client.get("/admin/integrity/non-conforming.upl").status_code == 403


# ----------------------------------------------------------- misplaced songs
def test_integrity_view_shows_misplaced_songs(admin_client):
    r = admin_client.get("/admin/integrity")
    assert "Misplaced songs" in r.text
    assert "30 Seconds to Mars - Attack" in r.text
    assert "The Kill" in r.text
    assert "30 Seconds to Mars - The Kill" in r.text  # expected folder


def test_integrity_view_links_to_misplaced_upl_export(admin_client):
    r = admin_client.get("/admin/integrity")
    assert "/admin/integrity/misplaced.upl" in r.text


def test_misplaced_upl_export_downloads_playlist(admin_client):
    r = admin_client.get("/admin/integrity/misplaced.upl")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    assert r.headers["content-type"].startswith("text/plain")
    assert "30 Seconds to Mars : The Kill" in r.text


def test_misplaced_upl_export_requires_admin(admin_client):
    admin_client.post("/admin/users", data={"username": "fay", "password": "fayfayfayfay"})
    admin_client.post("/logout")
    admin_client.post("/login", data={"username": "fay", "password": "fayfayfayfay"}, follow_redirects=False)
    assert admin_client.get("/admin/integrity/misplaced.upl").status_code == 403
