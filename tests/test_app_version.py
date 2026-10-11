"""Tests for the app's build version (app/__init__.py): the container image
gets it at build time as APP_VERSION (the GHCR version tag, e.g.
2026.10.11-42 or 1.2.0 - see .github/workflows/docker-publish.yml), a run
outside such an image reports "dev". Admins see it in the page footer.
"""

from __future__ import annotations

import app as app_package
from app.main import app

_VERSION_MARK = 'class="footer-version"'


def test_build_version_reads_app_version():
    assert app_package.build_version({"APP_VERSION": "2026.10.11-42"}) == "2026.10.11-42"


def test_build_version_falls_back_to_dev():
    assert app_package.build_version({}) == "dev"
    assert app_package.build_version({"APP_VERSION": "  "}) == "dev"


def test_fastapi_reports_the_build_version():
    assert app.version == app_package.__version__


def test_admin_sees_the_version_in_the_footer(admin_client):
    r = admin_client.get("/songs")
    assert f'{_VERSION_MARK}>v{app_package.__version__}</span>' in r.text


def test_regular_user_does_not_see_the_version(admin_client):
    admin_client.post("/admin/users", data={"username": "gus", "password": "gusgusgusgus"})
    admin_client.post("/logout")
    admin_client.post("/login", data={"username": "gus", "password": "gusgusgusgus"}, follow_redirects=False)
    assert _VERSION_MARK not in admin_client.get("/songs").text


def test_logged_out_visitor_does_not_see_the_version(client):
    assert _VERSION_MARK not in client.get("/login").text
