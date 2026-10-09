"""Route-level tests for the admin integrity/structure-check view."""

from __future__ import annotations


def test_integrity_view_has_a_rescan_button(admin_client):
    r = admin_client.get("/admin/integrity")
    assert r.status_code == 200
    assert 'href="/admin/integrity"' in r.text
    assert "Rescan" in r.text


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


def test_integrity_view_links_to_moves_export(admin_client):
    r = admin_client.get("/admin/integrity")
    assert "/admin/integrity/non-conforming.moves" in r.text


def test_structure_moves_export_lists_the_nested_subfolder(admin_client):
    r = admin_client.get("/admin/integrity/non-conforming.moves")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    tokens = [t for t in r.content.split(b"\x00") if t]
    # "Coverband - Import Batch" / CD1 from conftest.py, moved up to the base
    # path - paths are root-relative, not absolute (see app/move_export.py)
    assert b"Coverband - Import Batch/CD1" in tokens
    assert b"CD1" in tokens


def test_structure_moves_export_requires_admin(admin_client):
    admin_client.post("/admin/users", data={"username": "erin", "password": "erinerinerin"})
    admin_client.post("/logout")
    admin_client.post("/login", data={"username": "erin", "password": "erinerinerin"}, follow_redirects=False)
    assert admin_client.get("/admin/integrity/non-conforming.moves").status_code == 403


# ----------------------------------------------------------- misplaced songs
def test_integrity_view_shows_misplaced_songs(admin_client):
    r = admin_client.get("/admin/integrity")
    assert "Misplaced songs" in r.text
    assert "30 Seconds to Mars - Attack" in r.text
    assert "The Kill" in r.text
    assert "30 Seconds to Mars - The Kill" in r.text  # expected folder


def test_integrity_view_links_to_misplaced_moves_export(admin_client):
    r = admin_client.get("/admin/integrity")
    assert "/admin/integrity/misplaced.moves" in r.text


def test_misplaced_moves_export_lists_source_and_destination(admin_client):
    r = admin_client.get("/admin/integrity/misplaced.moves")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    tokens = [t for t in r.content.split(b"\x00") if t]
    # "30 Seconds to Mars - Attack" / TheKill.txt from conftest.py
    assert any(t.endswith(b"30 Seconds to Mars - Attack/TheKill.txt") for t in tokens)
    assert any(t.endswith(b"30 Seconds to Mars - The Kill/TheKill.txt") for t in tokens)


# ---------------------------------------------------- song file format .upl
def test_integrity_view_links_to_format_issues_upl_export(admin_client):
    r = admin_client.get("/admin/integrity")
    assert "/admin/integrity/format-issues.upl" in r.text


def test_format_issues_upl_export_downloads_playlist(admin_client):
    r = admin_client.get("/admin/integrity/format-issues.upl")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    assert r.headers["content-type"].startswith("text/plain")
    body = r.text
    assert "#Ultrastar Deluxe Playlist Format v1.0" in body
    # "Testband - Multi Song" folders have no #MP3/#AUDIO reference (see conftest.py)
    assert "Testband : Song A" in body


def test_format_issues_upl_export_requires_admin(admin_client):
    admin_client.post("/admin/users", data={"username": "ivy", "password": "ivyivyivyivy"})
    admin_client.post("/logout")
    admin_client.post("/login", data={"username": "ivy", "password": "ivyivyivyivy"}, follow_redirects=False)
    assert admin_client.get("/admin/integrity/format-issues.upl").status_code == 403


def test_misplaced_moves_export_requires_admin(admin_client):
    admin_client.post("/admin/users", data={"username": "fay", "password": "fayfayfayfay"})
    admin_client.post("/logout")
    admin_client.post("/login", data={"username": "fay", "password": "fayfayfayfay"}, follow_redirects=False)
    assert admin_client.get("/admin/integrity/misplaced.moves").status_code == 403


# ------------------------------------------- format table: counter + filter
def test_format_table_shows_how_many_song_files_are_affected(admin_client):
    from app import format_check

    total = len(format_check.check_library())
    r = admin_client.get("/admin/integrity")
    assert f"{total} song files affected" in r.text


def test_format_table_offers_a_filter_by_issue_type_with_counts(admin_client):
    from app import format_check

    counts = dict(format_check.issue_kind_counts(format_check.check_library()))
    r = admin_client.get("/admin/integrity")
    assert 'name="issue"' in r.text
    assert f"No audio reference ({counts['No audio reference']})" in r.text


def test_format_table_filtered_by_issue_type(admin_client):
    from app import format_check

    reports = format_check.check_library()
    wanted = format_check.filter_reports(reports, "No audio reference")
    r = admin_client.get("/admin/integrity", params={"issue": "No audio reference"})
    assert f"{len(wanted)} of {len(reports)} song files affected" in r.text
    assert '<option value="No audio reference" selected>' in r.text


def test_format_table_filter_with_no_matches(admin_client):
    r = admin_client.get("/admin/integrity", params={"issue": "Malformed #YEAR"})
    assert "0 of" in r.text
    assert "No song files with this issue." in r.text
