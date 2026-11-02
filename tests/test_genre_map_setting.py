"""Tests for "Genres on the map" on the admin Settings page
(AppSettings.genre_map_size, app/genre_layout.py): how many of the biggest
genres get their own cluster on the Genres page's Map tab and their own
circle and tile on its Connections tab - the others fold into "Other
genres". A whole number from 1 to MAX_GENRE_MAP_SIZE, 12 by default.
"""

from __future__ import annotations

import pytest

from app.app_settings import get_app_settings
from app.database import SessionLocal
from app.genre_layout import DEFAULT_GENRE_MAP_SIZE, MAX_GENRE_MAP_SIZE


def _save(admin_client, **overrides):
    data = {"request_profile": "karaoke_night", "report_profile": "strict", "mode": "production",
            "logging_enabled": "on", **overrides}
    return admin_client.post("/admin/settings", data=data, follow_redirects=False)


def _stored() -> int:
    with SessionLocal() as db:
        return get_app_settings(db).genre_map_size


def test_the_default_is_twelve(admin_client):
    assert DEFAULT_GENRE_MAP_SIZE == 12
    assert _stored() == 12
    assert 'name="genre_map_size" value="12"' in admin_client.get("/admin/settings").text


def test_saving_a_number_stores_it(admin_client):
    assert _save(admin_client, genre_map_size=" 8 ").status_code == 303
    assert _stored() == 8


@pytest.mark.parametrize("value", ["0", str(MAX_GENRE_MAP_SIZE + 1), "abc", " ", "2.5"])
def test_an_invalid_number_is_refused_and_nothing_changes(admin_client, value):
    r = _save(admin_client, genre_map_size=value, mode="debug")
    assert r.status_code == 422
    assert f"<li>Genres on the map must be a whole number from 1 to {MAX_GENRE_MAP_SIZE}.</li>" in r.text
    assert _stored() == 12


def test_saving_without_the_field_keeps_the_number(admin_client):
    _save(admin_client, genre_map_size="5")
    _save(admin_client)
    assert _stored() == 5


def test_the_settings_page_has_no_map_spacing_fields(admin_client):
    html = admin_client.get("/admin/settings").text
    assert 'name="genre_map_gap"' not in html
    assert 'name="genre_map_overlap"' not in html
