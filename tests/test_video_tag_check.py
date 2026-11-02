"""Tests for the #VIDEO tag checks in app/format_check.py, on top of the
existing "#VIDEO file not found": a song .txt without a #VIDEO tag (or an
empty one) is an error of kind "Missing #VIDEO", and additionally of kind
"Video file not referenced" when a video file sits in its folder.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app import format_check

HEADER = "#VERSION:1.0.0\n#TITLE:Faithfully\n#ARTIST:Journey\n#MP3:song.mp3\n#BPM:200\n#GAP:0\n"
BODY = ": 0 4 0 La\nE\n"


def _song(tmp_path: Path, extra_header: str = "", files: tuple[str, ...] = ()) -> Path:
    (tmp_path / "song.mp3").write_bytes(b"fake-mp3")
    for name in files:
        (tmp_path / name).write_bytes(b"fake")
    path = tmp_path / "song.txt"
    path.write_text(HEADER + extra_header + BODY, encoding="utf-8")
    return path


def _kinds(path: Path) -> dict[str, str]:
    return {i.kind: i.severity for i in format_check.check_file(path).issues}


def test_a_song_with_its_video_referenced_is_clean(tmp_path):
    assert format_check.check_file(_song(tmp_path, "#VIDEO:song.mp4\n", files=("song.mp4",))).issues == []


@pytest.mark.parametrize("extra_header", ["", "#VIDEO:\n", "#VIDEO:   \n"])
def test_a_missing_or_empty_video_tag_is_an_error(tmp_path, extra_header):
    issues = format_check.check_file(_song(tmp_path, extra_header)).issues
    assert [(i.kind, i.severity, i.message) for i in issues] == [
        ("Missing #VIDEO", "error", "Missing #VIDEO tag.")]


@pytest.mark.parametrize("video", ["song.mp4", "clip.MKV", "v.avi", "v.webm", "v.mpg", "v.mpeg", "v.m4v",
                                   "v.mov", "v.flv", "v.divx", "v.wmv"])
def test_an_unreferenced_video_in_the_folder_is_also_reported(tmp_path, video):
    issues = format_check.check_file(_song(tmp_path, files=(video,))).issues
    assert {i.kind: i.severity for i in issues} == {"Missing #VIDEO": "error", "Video file not referenced": "error"}
    message = next(i.message for i in issues if i.kind == "Video file not referenced")
    assert message == f"A video file is in the folder but not referenced by #VIDEO: {video!r}."


def test_several_unreferenced_videos_are_named_in_one_issue(tmp_path):
    issues = format_check.check_file(_song(tmp_path, files=("b.mp4", "a.mkv"))).issues
    unreferenced = [i for i in issues if i.kind == "Video file not referenced"]
    assert [i.message for i in unreferenced] == [
        "A video file is in the folder but not referenced by #VIDEO: 'a.mkv', 'b.mp4'."]


def test_other_files_and_subfolders_are_not_videos(tmp_path):
    (tmp_path / "extra.mp4").mkdir()
    path = _song(tmp_path, files=("cover.jpg", "notes.mp4.txt", "song.opus"))
    assert _kinds(path) == {"Missing #VIDEO": "error"}


def test_a_video_tag_naming_a_missing_file_keeps_its_own_kind(tmp_path):
    path = _song(tmp_path, "#VIDEO:gone.mp4\n", files=("other.mp4",))
    assert _kinds(path) == {"#VIDEO file not found": "error"}


def test_check_library_lists_a_song_whose_only_issue_is_the_missing_tag(tmp_path):
    folder = tmp_path / "Journey - Faithfully"
    folder.mkdir()
    _song(folder)
    reports = format_check.check_library(tmp_path)
    assert [(r.folder, [i.kind for i in r.issues]) for r in reports] == [
        ("Journey - Faithfully", ["Missing #VIDEO"])]
