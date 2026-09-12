"""Tests for app/structure_check.py: flags song folders that don't follow
the flat "Artist - Title" convention, or that contain nested subfolders -
both introduced by other library-management tools - for the admin integrity
view's structure report.
"""

from __future__ import annotations

from app import structure_check


def test_conforming_flat_folder_has_no_issue(tmp_path):
    (tmp_path / "Queen - Bohemian Rhapsody").mkdir()
    issues = structure_check.check_structure(root=tmp_path)
    assert issues == []


def test_folder_without_separator_is_flagged(tmp_path):
    (tmp_path / "PlainFolderNoSeparator").mkdir()
    issues = structure_check.check_structure(root=tmp_path)
    assert len(issues) == 1
    assert issues[0].folder == "PlainFolderNoSeparator"
    assert any("Artist" in r or "name" in r.lower() for r in issues[0].reasons)


def test_folder_with_nested_subfolder_is_flagged(tmp_path):
    top = tmp_path / "Coverband - Import Batch"
    top.mkdir()
    (top / "CD1").mkdir()
    issues = structure_check.check_structure(root=tmp_path)
    assert len(issues) == 1
    assert issues[0].folder == "Coverband - Import Batch"
    assert any("CD1" in r for r in issues[0].reasons)


def test_conforming_folder_with_multiple_song_files_has_no_issue(tmp_path):
    # a folder may bundle several distinct songs - that's fine, only nested
    # *subfolders* and a non-conforming folder *name* are issues.
    folder = tmp_path / "Testband - Multi Song"
    folder.mkdir()
    (folder / "SongA.txt").write_text("x", encoding="utf-8")
    (folder / "SongB.txt").write_text("x", encoding="utf-8")
    issues = structure_check.check_structure(root=tmp_path)
    assert issues == []


def test_ignored_and_hidden_folders_are_skipped(tmp_path):
    (tmp_path / "@eaDir").mkdir()
    (tmp_path / ".hidden").mkdir()
    issues = structure_check.check_structure(root=tmp_path)
    assert issues == []


def test_folder_tree_lists_nested_contents(tmp_path):
    top = tmp_path / "Coverband - Import Batch"
    top.mkdir()
    nested = top / "CD1"
    nested.mkdir()
    (nested / "Song.txt").write_text("x", encoding="utf-8")

    lines = structure_check.folder_tree("Coverband - Import Batch", root=tmp_path)
    joined = "\n".join(lines)
    assert "CD1" in joined
    assert "Song.txt" in joined
