"""Tests for app/upl_export.py: builds an UltraStar Deluxe Playlist (.upl)
file - the format UltraStar Manager actually supports as input (see
third_party/ultrastar-manager/src/playlist/QUPlaylistFile.cpp, which matches
playlist entries by Artist + Title) - scoped to the songs the song-file-
format check has flagged, so an admin can jump straight to just those in
UltraStar Manager instead of the whole library. The structure/misplaced-
songs sections export a move list instead (see app/move_export.py,
tests/test_move_export.py) - UltraStar Manager can't move files.
"""

from __future__ import annotations

from app import format_check, upl_export


def test_build_format_issues_upl_includes_flagged_files(tmp_path):
    folder = tmp_path / "Solo - Song"
    folder.mkdir()
    (folder / "song.mp3").write_bytes(b"fake-mp3")
    (folder / "Song.txt").write_text(
        "#VERSION:1.0.0\n#TITLE:X\n#ARTIST:Y\n#MP3:song.mp3\n#BPM:not-a-number\n#GAP:0\n: 0 4 0 La\nE\n",
        encoding="utf-8",
    )
    reports = format_check.check_library(root=tmp_path)
    content = upl_export.build_format_issues_upl(reports, root=tmp_path)
    assert "#Ultrastar Deluxe Playlist Format v1.0" in content
    assert "Y : X" in content


def test_build_format_issues_upl_skips_files_missing_artist_or_title(tmp_path):
    folder = tmp_path / "Bad - Song"
    folder.mkdir()
    (folder / "Song.txt").write_text("#GENRE:Rock\nE\n", encoding="utf-8")
    reports = format_check.check_library(root=tmp_path)
    content = upl_export.build_format_issues_upl(reports, root=tmp_path)
    assert content.endswith("#Songs:\n")


def test_build_format_issues_upl_with_no_issues_has_empty_song_list(tmp_path):
    content = upl_export.build_format_issues_upl([], root=tmp_path)
    assert content.endswith("#Songs:\n")
