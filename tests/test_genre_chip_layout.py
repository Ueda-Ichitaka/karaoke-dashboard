"""Tests for where the genre chips of a song row sit on the Genres page's
List tab (.genre-song in app/static/style.css): on the right edge of the
row, also when they wrap under the title, so every row lines up; on a phone
(the 640px breakpoint of the phone layout) every row has its chips under
the title, on the left. The song card of the Map and Connections tabs
keeps its chips on the left. On the Edit tab, what a row hides (its
buttons in display mode) stays hidden.
"""

from __future__ import annotations

import re
from pathlib import Path

CSS = (Path(__file__).resolve().parents[1] / "app" / "static" / "style.css").read_text()


def _rule(css: str, selector: str) -> str:
    """The declarations of the rule for exactly this selector."""
    match = re.search(r"(?:^|[}\s])" + re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert match, f"no rule for {selector}"
    return match.group(1)


def _media(width: int) -> str:
    """Everything inside the @media (max-width: <width>px) blocks."""
    blocks = []
    for start in [m.end() for m in re.finditer(rf"@media \(max-width: {width}px\)\s*\{{", CSS)]:
        depth, i = 1, start
        while depth:
            depth += {"{": 1, "}": -1}.get(CSS[i], 0)
            i += 1
        blocks.append(CSS[start:i - 1])
    return "\n".join(blocks)


def _top_level() -> str:
    return re.sub(r"@media[^{]*\{(?:[^{}]*\{[^}]*\})*\s*\}", "", CSS)


def test_the_chips_sit_on_the_right_also_when_they_wrap():
    chips = _rule(_top_level(), ".genre-song .genre-chips")
    assert "margin-left: auto" in chips
    assert "justify-content: flex-end" in chips


def test_the_song_card_keeps_its_chips_on_the_left():
    assert "justify-content" not in _rule(_top_level(), ".genre-chips")


def test_on_a_phone_every_row_has_its_chips_under_the_title_on_the_left():
    phone = _media(640)
    assert "flex-direction: column" in _rule(phone, ".genre-song")
    assert "align-items: flex-start" in _rule(phone, ".genre-song")
    chips = _rule(phone, ".genre-song .genre-chips")
    assert "margin-left: 0" in chips
    assert "justify-content: flex-start" in chips


def test_hidden_parts_of_a_genre_edit_row_stay_hidden():
    """The row's buttons are .btn (display: inline-flex), which would show them
    despite the hidden attribute app/static/app.js sets."""
    assert "display: none" in _rule(_top_level(), ".genre-edit-row [hidden]")
