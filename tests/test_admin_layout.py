"""Tests that the admin report/request list views opt into the wide content
layout (see app/static/style.css's .content.wide) so their tables can use
the full browser window width instead of being capped at the default
960px reading-width column.
"""

from __future__ import annotations


def test_admin_reports_view_uses_wide_content_layout(admin_client):
    r = admin_client.get("/admin/reports")
    assert '<main class="content wide">' in r.text


def test_admin_requests_view_uses_wide_content_layout(admin_client):
    r = admin_client.get("/admin/requests")
    assert '<main class="content wide">' in r.text


def test_regular_pages_keep_the_default_content_width(admin_client):
    r = admin_client.get("/report")
    assert '<main class="content">' in r.text
