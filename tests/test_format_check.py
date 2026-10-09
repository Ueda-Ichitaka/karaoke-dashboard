"""Tests for app/format_check.py: validates one UltraStar .txt file against
the format spec (https://github.com/UltraStar-Deluxe/format), for the admin
integrity view.
"""

from __future__ import annotations

from pathlib import Path

from app import format_check


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_valid_file_has_no_issues(tmp_path):
    (tmp_path / "song.mp3").write_bytes(b"fake-mp3")
    path = _write(
        tmp_path, "song.txt",
        "#VERSION:1.0.0\n#TITLE:Bohemian Rhapsody\n#ARTIST:Queen\n#MP3:song.mp3\n"
        "#BPM:200\n#GAP:0\n: 0 4 0 La\nE\n",
    )
    report = format_check.check_file(path)
    assert report.issues == []


def test_non_ultrastar_text_file_is_skipped(tmp_path):
    path = _write(tmp_path, "readme.txt", "just some notes, not a song file\n")
    report = format_check.check_file(path)
    assert report.issues == []


def test_missing_mandatory_tags_are_errors(tmp_path):
    path = _write(tmp_path, "song.txt", "#GENRE:Rock\nE\n")
    report = format_check.check_file(path)
    messages = [i.message for i in report.issues if i.severity == "error"]
    assert any("TITLE" in m for m in messages)
    assert any("ARTIST" in m for m in messages)
    assert any("BPM" in m for m in messages)
    assert any("MP3" in m or "AUDIO" in m for m in messages)


def test_missing_version_is_a_warning_not_an_error(tmp_path):
    (tmp_path / "song.mp3").write_bytes(b"fake-mp3")
    path = _write(
        tmp_path, "song.txt",
        "#TITLE:X\n#ARTIST:Y\n#MP3:song.mp3\n#BPM:200\n#GAP:0\n: 0 4 0 La\nE\n",
    )
    report = format_check.check_file(path)
    assert not report.has_errors
    assert any(i.severity == "warning" and "VERSION" in i.message for i in report.issues)


def test_missing_referenced_media_file_is_an_error(tmp_path):
    path = _write(
        tmp_path, "song.txt",
        "#VERSION:1.0.0\n#TITLE:X\n#ARTIST:Y\n#MP3:missing.mp3\n"
        "#BPM:200\n#GAP:0\n: 0 4 0 La\nE\n",
    )
    report = format_check.check_file(path)
    assert report.has_errors
    assert any("missing.mp3" in i.message for i in report.issues if i.severity == "error")


def test_malformed_bpm_is_a_warning(tmp_path):
    (tmp_path / "song.mp3").write_bytes(b"fake-mp3")
    path = _write(
        tmp_path, "song.txt",
        "#VERSION:1.0.0\n#TITLE:X\n#ARTIST:Y\n#MP3:song.mp3\n"
        "#BPM:not-a-number\n#GAP:0\n: 0 4 0 La\nE\n",
    )
    report = format_check.check_file(path)
    assert any(i.severity == "warning" and "BPM" in i.message for i in report.issues)


def test_voice_change_without_matching_header_is_a_warning(tmp_path):
    (tmp_path / "song.mp3").write_bytes(b"fake-mp3")
    path = _write(
        tmp_path, "song.txt",
        "#VERSION:1.0.0\n#TITLE:X\n#ARTIST:Y\n#MP3:song.mp3\n#BPM:200\n#GAP:0\n"
        "P1\n: 0 4 0 La\nP2\n: 4 4 0 La\nE\n",
    )
    report = format_check.check_file(path)
    assert any(i.severity == "warning" and "P2" in i.message for i in report.issues)


def test_unrecognized_body_line_is_a_warning(tmp_path):
    (tmp_path / "song.mp3").write_bytes(b"fake-mp3")
    path = _write(
        tmp_path, "song.txt",
        "#VERSION:1.0.0\n#TITLE:X\n#ARTIST:Y\n#MP3:song.mp3\n#BPM:200\n#GAP:0\n"
        "???not a note line\nE\n",
    )
    report = format_check.check_file(path)
    assert any(i.severity == "warning" and "unrecognized" in i.message.lower() for i in report.issues)


def test_empty_body_is_an_error(tmp_path):
    (tmp_path / "song.mp3").write_bytes(b"fake-mp3")
    path = _write(
        tmp_path, "song.txt",
        "#VERSION:1.0.0\n#TITLE:X\n#ARTIST:Y\n#MP3:song.mp3\n#BPM:200\n#GAP:0\nE\n",
    )
    report = format_check.check_file(path)
    assert any(i.severity == "error" and "note" in i.message.lower() for i in report.issues)


def test_check_library_only_reports_files_with_issues(tmp_path):
    good_dir = tmp_path / "Good - Song"
    good_dir.mkdir()
    (good_dir / "song.mp3").write_bytes(b"fake-mp3")
    (good_dir / "Song.txt").write_text(
        "#VERSION:1.0.0\n#TITLE:X\n#ARTIST:Y\n#MP3:song.mp3\n#BPM:200\n#GAP:0\n: 0 4 0 La\nE\n",
        encoding="utf-8",
    )
    bad_dir = tmp_path / "Bad - Song"
    bad_dir.mkdir()
    (bad_dir / "Song.txt").write_text("#GENRE:Rock\nE\n", encoding="utf-8")

    reports = format_check.check_library(root=tmp_path)
    folders = {r.folder for r in reports}
    assert folders == {"Bad - Song"}


def test_check_library_hides_a_file_whose_only_issue_is_missing_version(tmp_path):
    # Missing #VERSION is real but non-breaking - a report listing hundreds
    # of these (common on an older library) drowns out actual problems.
    folder = tmp_path / "Solo - Song"
    folder.mkdir()
    (folder / "song.mp3").write_bytes(b"fake-mp3")
    (folder / "Song.txt").write_text(
        "#TITLE:X\n#ARTIST:Y\n#MP3:song.mp3\n#BPM:200\n#GAP:0\n: 0 4 0 La\nE\n",
        encoding="utf-8",
    )
    reports = format_check.check_library(root=tmp_path)
    assert reports == []


def test_check_library_still_shows_version_warning_alongside_a_real_issue(tmp_path):
    # Missing #VERSION plus a genuine error: the file must still be reported,
    # and the VERSION warning still shown for context.
    folder = tmp_path / "Solo - Song"
    folder.mkdir()
    (folder / "Song.txt").write_text("#TITLE:X\n#ARTIST:Y\n#BPM:200\n#GAP:0\n: 0 4 0 La\nE\n", encoding="utf-8")
    reports = format_check.check_library(root=tmp_path)
    assert len(reports) == 1
    messages = [i.message for i in reports[0].issues]
    assert any("VERSION" in m for m in messages)
    assert any("audio" in m.lower() for m in messages)


# ------------------------------------------------------ issue kinds + filter
# Every issue carries a stable "kind" (its type, without file names or line
# details) so the integrity view can filter the table by issue type.
def _song(folder: Path, body_tags: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "song.txt").write_text(
        f"#VERSION:1.0.0\n#TITLE:T\n#ARTIST:A\n{body_tags}#GAP:0\n: 0 4 0 La\nE\n", encoding="utf-8"
    )


def test_each_issue_has_a_stable_kind(tmp_path):
    path = _write(
        tmp_path, "song.txt",
        "#TITLE:T\n#ARTIST:A\n#MP3:missing.mp3\n#VIDEO:gone.mp4\n#BPM:abc\n#GAP:0\nP2\nxyz\nE\n",
    )
    kinds = {i.kind for i in format_check.check_file(path).issues}
    assert kinds == {
        "Missing #VERSION", "Malformed #BPM", "#MP3 file not found", "#VIDEO file not found",
        "Voice change without header", "Unrecognized body line", "No note lines",
    }
    no_audio = _write(tmp_path, "b.txt", "#VERSION:1\n#ARTIST:A\n#BPM:1\n#GAP:0\n: 0 1 0 a\n")
    assert {i.kind for i in format_check.check_file(no_audio).issues} == {"Missing #TITLE", "No audio reference"}


def test_issue_kind_counts_count_files_most_common_first(tmp_path):
    _song(tmp_path / "A - One", "#BPM:1\n")  # no audio reference
    _song(tmp_path / "A - Two", "#BPM:1\n")  # no audio reference
    _song(tmp_path / "A - Three", "#MP3:gone.mp3\n#BPM:x\n")  # missing file + malformed BPM
    reports = format_check.check_library(root=tmp_path)
    assert format_check.issue_kind_counts(reports) == [
        ("No audio reference", 2), ("#MP3 file not found", 1), ("Malformed #BPM", 1),
    ]


def test_filter_reports_keeps_only_files_with_that_kind(tmp_path):
    _song(tmp_path / "A - One", "#BPM:1\n")
    _song(tmp_path / "A - Three", "#MP3:gone.mp3\n#BPM:x\n")
    reports = format_check.check_library(root=tmp_path)
    filtered = format_check.filter_reports(reports, "Malformed #BPM")
    assert [r.folder for r in filtered] == ["A - Three"]
    assert format_check.filter_reports(reports, "") == reports
