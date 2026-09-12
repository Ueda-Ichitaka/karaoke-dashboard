"""Tests for app/upl_export.py: builds an UltraStar Deluxe Playlist (.upl)
file - the format UltraStar Manager actually supports as input (see
third_party/ultrastar-manager/src/playlist/QUPlaylistFile.cpp, which matches
playlist entries by Artist + Title) - scoped to the songs found inside
non-conforming library folders, so an admin can jump straight to just those
in UltraStar Manager instead of the whole library.
"""

from __future__ import annotations

from app import structure_check, upl_export
from app.misplaced_check import MisplacedSong


def test_build_upl_includes_songs_from_non_conforming_folders(tmp_path):
    top = tmp_path / "Coverband - Import Batch"
    top.mkdir()
    nested = top / "CD1"
    nested.mkdir()
    (nested / "Track.txt").write_text(
        "#TITLE:Track\n#ARTIST:Coverband\n#BPM:120\n#GAP:0\nE\n", encoding="utf-8"
    )

    issues = structure_check.check_structure(root=tmp_path)
    content = upl_export.build_upl(issues, root=tmp_path)

    assert content.startswith("######################################\n")
    assert "#Ultrastar Deluxe Playlist Format v1.0" in content
    assert "#Songs:" in content
    assert "Coverband : Track" in content


def test_build_upl_skips_songs_missing_artist_or_title(tmp_path):
    top = tmp_path / "Bad - Folder"
    top.mkdir()
    (top / "sub").mkdir()
    (top / "sub" / "NoTags.txt").write_text("#BPM:120\n#GAP:0\nE\n", encoding="utf-8")

    issues = structure_check.check_structure(root=tmp_path)
    content = upl_export.build_upl(issues, root=tmp_path)

    assert "#Songs:" in content
    assert " : \n" not in content  # no bogus blank entry for the untagged file


def test_build_upl_with_no_issues_has_empty_song_list(tmp_path):
    (tmp_path / "Queen - Bohemian Rhapsody").mkdir()
    issues = structure_check.check_structure(root=tmp_path)
    assert issues == []

    content = upl_export.build_upl(issues, root=tmp_path)
    assert content.endswith("#Songs:\n")


def test_build_misplaced_upl_lists_each_song_by_its_own_artist_title():
    songs = [
        MisplacedSong(
            folder="30 Seconds to Mars - Attack", source_file="KingsAndQueens.txt",
            artist="30 Seconds to Mars", title="Kings and Queens",
            expected_folder="30 Seconds to Mars - Kings and Queens",
        ),
    ]
    content = upl_export.build_misplaced_upl(songs)
    assert "#Ultrastar Deluxe Playlist Format v1.0" in content
    assert "#Songs:" in content
    assert "30 Seconds to Mars : Kings and Queens" in content


def test_build_misplaced_upl_with_no_songs_has_empty_song_list():
    content = upl_export.build_misplaced_upl([])
    assert content.endswith("#Songs:\n")
