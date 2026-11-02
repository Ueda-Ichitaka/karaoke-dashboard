"""Tests for how /static files are cached (app/static_files.py): every
response says Cache-Control: no-cache, so a browser asks again on each page
load and gets the new CSS and JavaScript right after an image update - a
cheap 304 when the file is unchanged.
"""

from __future__ import annotations

import pytest


@pytest.mark.parametrize("path", ["/static/style.css", "/static/app.js"])
def test_static_files_must_be_revalidated(client, path):
    r = client.get(path)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-cache"


def test_an_unchanged_file_is_a_304_that_still_says_no_cache(client):
    etag = client.get("/static/style.css").headers["etag"]
    r = client.get("/static/style.css", headers={"If-None-Match": etag})
    assert r.status_code == 304
    assert r.headers["cache-control"] == "no-cache"
