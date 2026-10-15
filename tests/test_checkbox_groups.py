"""Tests for the trait checkbox group's "None" choice on the admin edit forms:
in the browser (app/static/checkbox-groups.js), checking a trait unchecks
"None", checking "None" unchecks every trait, and unchecking the last trait
checks "None" again. The server (app/traits.py: format_traits) drops a
"None" that still arrives together with a trait, e.g. without JS.

The script's rule is run under node (skipped where node isn't installed).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app import traits
from app.database import SessionLocal
from app.models import PendingSongRequest

_SCRIPT = Path(__file__).resolve().parent.parent / "app" / "static" / "checkbox-groups.js"


def _apply(boxes: dict[str, bool], changed: str) -> dict[str, bool]:
    """Runs exclusiveChoice() under node: `boxes` is the state right after the
    click on `changed`, the result the state the script leaves behind."""
    if shutil.which("node") is None:
        pytest.skip("node is not installed")
    program = f"""
        const {{ exclusiveChoice }} = require({json.dumps(str(_SCRIPT))});
        const boxes = Object.entries({json.dumps(boxes)}).map(([value, checked]) => ({{ value, checked }}));
        exclusiveChoice(boxes, boxes.find((b) => b.value === {json.dumps(changed)}), "none");
        console.log(JSON.stringify(Object.fromEntries(boxes.map((b) => [b.value, b.checked]))));
    """
    out = subprocess.run(["node", "-e", program], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def test_checking_a_trait_unchecks_none():
    state = _apply({"none": True, "harsh_vocals": True, "choir": False}, "harsh_vocals")
    assert state == {"none": False, "harsh_vocals": True, "choir": False}


def test_checking_none_unchecks_every_trait():
    state = _apply({"none": True, "harsh_vocals": True, "choir": True}, "none")
    assert state == {"none": True, "harsh_vocals": False, "choir": False}


def test_unchecking_the_last_trait_checks_none_again():
    state = _apply({"none": False, "harsh_vocals": False, "choir": False}, "harsh_vocals")
    assert state == {"none": True, "harsh_vocals": False, "choir": False}


def test_unchecking_one_of_several_traits_leaves_none_unchecked():
    state = _apply({"none": False, "harsh_vocals": False, "choir": True}, "harsh_vocals")
    assert state == {"none": False, "harsh_vocals": False, "choir": True}


def test_edit_forms_mark_the_trait_group_and_load_the_script(admin_client):
    admin_client.post("/request", data={"band_name": "Journey", "song_name": "Faithfully"})
    with SessionLocal() as db:
        pid = db.query(PendingSongRequest).one().id
    html = admin_client.get(f"/admin/requests/pending/{pid}/edit").text
    assert 'data-exclusive-choice="none"' in html
    assert '<script src="/static/checkbox-groups.js" defer></script>' in html


def test_format_traits_drops_none_next_to_a_trait():
    assert traits.format_traits(["none", "harsh_vocals"]) == "harsh_vocals"
    assert traits.format_traits(["none"]) == "none"
    assert traits.format_traits([]) == "none"
