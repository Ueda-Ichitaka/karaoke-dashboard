"""Tests for app/move_export.py: the NUL-delimited source/destination move
lists that scripts/apply_moves.sh (a standalone bash script, not part of
the app) consumes to do what UltraStar Manager's own .upl playlist export
never could - actually move misplaced songs and non-conforming nested
subfolders on disk. Replaces the old .upl export for those two integrity-
view sections only (see app/upl_export.py, still used for song-file-format
issues).
"""

from __future__ import annotations

from pathlib import Path

from app import misplaced_check, structure_check
from app.move_export import build_misplaced_moves, build_structure_moves, sanitize_folder_component


def _write_song(folder: Path, filename: str, artist: str, title: str, extra: str = "") -> None:
    (folder / filename).write_text(
        f"#TITLE:{title}\n#ARTIST:{artist}\n{extra}#BPM:120\n#GAP:0\nE\n", encoding="utf-8"
    )


def _pairs(blob: bytes) -> list[tuple[str, str]]:
    tokens = [t for t in blob.decode("utf-8").split("\x00") if t]
    assert len(tokens) % 2 == 0
    return list(zip(tokens[0::2], tokens[1::2], strict=True))


def test_sanitize_folder_component_replaces_slash():
    assert sanitize_folder_component("AC/DC") == "AC-DC"
    assert sanitize_folder_component("Queen") == "Queen"


def test_build_misplaced_moves_includes_the_txt_file(tmp_path):
    folder = tmp_path / "30 Seconds to Mars - Attack"
    folder.mkdir()
    _write_song(folder, "Attack.txt", "30 Seconds to Mars", "Attack")
    _write_song(folder, "TheKill.txt", "30 Seconds to Mars", "The Kill")

    songs = misplaced_check.find_misplaced_songs(root=tmp_path)
    pairs = _pairs(build_misplaced_moves(songs, root=tmp_path))
    assert len(pairs) == 1
    src, dst = pairs[0]
    assert src == str(folder / "TheKill.txt")
    assert dst == str(tmp_path / "30 Seconds to Mars - The Kill" / "TheKill.txt")


def test_build_misplaced_moves_includes_referenced_media_and_cover_files(tmp_path):
    folder = tmp_path / "30 Seconds to Mars - Attack"
    folder.mkdir()
    _write_song(folder, "Attack.txt", "30 Seconds to Mars", "Attack")
    _write_song(
        folder, "TheKill.txt", "30 Seconds to Mars", "The Kill",
        extra="#MP3:TheKill.mp3\n#COVER:TheKill [CO].jpg\n",
    )
    (folder / "TheKill.mp3").write_bytes(b"fake")
    (folder / "TheKill [CO].jpg").write_bytes(b"fake")

    songs = misplaced_check.find_misplaced_songs(root=tmp_path)
    pairs = _pairs(build_misplaced_moves(songs, root=tmp_path))
    sources = {src for src, _ in pairs}
    assert str(folder / "TheKill.txt") in sources
    assert str(folder / "TheKill.mp3") in sources
    assert str(folder / "TheKill [CO].jpg") in sources
    dest_folder = tmp_path / "30 Seconds to Mars - The Kill"
    assert (str(folder / "TheKill.mp3"), str(dest_folder / "TheKill.mp3")) in pairs


def test_build_misplaced_moves_sanitizes_a_slash_in_the_destination_folder(tmp_path):
    folder = tmp_path / "AC-DC - Highway to Hell"
    folder.mkdir()
    _write_song(folder, "Highway.txt", "AC/DC", "Highway to Hell")
    _write_song(folder, "BackInBlack.txt", "AC/DC", "Back in Black")

    songs = misplaced_check.find_misplaced_songs(root=tmp_path)
    pairs = _pairs(build_misplaced_moves(songs, root=tmp_path))
    assert len(pairs) == 1
    _, dst = pairs[0]
    assert dst == str(tmp_path / "AC-DC - Back in Black" / "BackInBlack.txt")


def test_build_misplaced_moves_empty_when_nothing_misplaced(tmp_path):
    folder = tmp_path / "Queen - Bohemian Rhapsody"
    folder.mkdir()
    _write_song(folder, "song.txt", "Queen", "Bohemian Rhapsody")
    songs = misplaced_check.find_misplaced_songs(root=tmp_path)
    assert build_misplaced_moves(songs, root=tmp_path) == b""


def test_build_structure_moves_moves_nested_subfolder_to_base(tmp_path):
    folder = tmp_path / "Coverband - Import Batch"
    folder.mkdir()
    cd1 = folder / "CD1"
    cd1.mkdir()
    _write_song(cd1, "Track.txt", "Coverband", "Track")

    issues = structure_check.check_structure(root=tmp_path)
    pairs = _pairs(build_structure_moves(issues, root=tmp_path))
    assert (str(cd1), str(tmp_path / "CD1")) in pairs


def test_build_structure_moves_ignores_a_folder_literally_named_dash(tmp_path):
    folder = tmp_path / "Coverband - Import Batch"
    folder.mkdir()
    (folder / "-").mkdir()
    (folder / "CD1").mkdir()
    _write_song(folder / "CD1", "Track.txt", "Coverband", "Track")

    issues = structure_check.check_structure(root=tmp_path)
    pairs = _pairs(build_structure_moves(issues, root=tmp_path))
    sources = {src for src, _ in pairs}
    assert str(folder / "-") not in sources
    assert str(folder / "CD1") in sources


def test_build_structure_moves_empty_when_nothing_nested(tmp_path):
    folder = tmp_path / "PlainFolderNoSeparator"
    folder.mkdir()
    issues = structure_check.check_structure(root=tmp_path)
    assert build_structure_moves(issues, root=tmp_path) == b""
