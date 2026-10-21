"""Tests for the library-scan utilities on the admin Settings page
(app/routes/admin.py): "Scan now" runs the library scan behind the songs
page's "Recently added"/"Recently updated" panels right away, and "Reset"
forgets everything recorded and scans again as a very first scan
(app/library_history.py).
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.database import SessionLocal
from app.models import LibraryFolder

SCAN, RESET = "/admin/settings/library-scan", "/admin/settings/library-reset"


def _first_seen() -> dict[str, datetime | None]:
    with SessionLocal() as db:
        return {row.folder: row.first_seen_at for row in db.query(LibraryFolder)}


def test_the_settings_page_offers_scan_now_and_a_confirmed_reset(admin_client):
    html = admin_client.get("/admin/settings").text
    assert f'action="{SCAN}"' in html
    assert f'action="{RESET}"' in html
    reset_form = html[html.index(f'action="{RESET}"') - 200:html.index(f'action="{RESET}"') + 200]
    assert "return confirm(" in reset_form


def test_scan_now_records_new_folders_and_says_so(admin_client):
    r = admin_client.post(SCAN, follow_redirects=False)
    assert (r.status_code, r.headers["location"]) == (303, "/admin/settings?library=scanned")
    assert set(_first_seen().values()) == {None}  # the very first scan: everything is old

    with SessionLocal() as db:
        db.query(LibraryFolder).filter_by(folder="Toto - Africa").delete()
        db.commit()
    admin_client.post(SCAN)
    assert _first_seen()["Toto - Africa"] is not None  # a folder the scan hasn't seen is new
    assert "Library scan done." in admin_client.get("/admin/settings?library=scanned").text


def test_reset_forgets_recorded_dates_and_counts_everything_as_old(admin_client):
    with SessionLocal() as db:
        db.add(LibraryFolder(folder="Toto - Africa", first_seen_at=datetime.now(UTC), follows_convention=True,
                             files="{}", updated_at=datetime.now(UTC)))
        db.add(LibraryFolder(folder="Gone - Folder", first_seen_at=datetime.now(UTC), files="{}"))
        db.commit()
    r = admin_client.post(RESET, follow_redirects=False)
    assert (r.status_code, r.headers["location"]) == (303, "/admin/settings?library=reset")
    seen = _first_seen()
    assert "Gone - Folder" not in seen
    assert seen["Toto - Africa"] is None
    with SessionLocal() as db:
        assert db.query(LibraryFolder).filter(LibraryFolder.updated_at.is_not(None)).count() == 0
    assert "Library history reset" in admin_client.get("/admin/settings?library=reset").text


def test_both_are_admin_only(admin_client):
    admin_client.post("/admin/users", data={"username": "gus", "password": "gusgusgusgus"})
    admin_client.post("/logout")
    admin_client.post("/login", data={"username": "gus", "password": "gusgusgusgus"}, follow_redirects=False)
    assert admin_client.post(SCAN).status_code == 403
    assert admin_client.post(RESET).status_code == 403
    assert _first_seen() == {}
