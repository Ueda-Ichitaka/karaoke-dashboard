"""Tests for scripts/fix_case_mismatches.py: the standalone, one-off fixer
for song files whose name on disk differs from their .txt's #MP3/#AUDIO/
#VIDEO/#COVER/#BACKGROUND tag only in letter case - left behind when
UltraStar Manager rewrote the tag over a case-insensitive SMB mount but the
case-only file rename itself was refused. Runs the real script via
subprocess against a throwaway tmp_path library.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fix_case_mismatches.py"


def _song(folder: Path, txt: str, tags: str, encoding: str = "utf-8", newline: str = "\n") -> None:
    folder.mkdir(parents=True, exist_ok=True)
    body = f"#TITLE:X\n#ARTIST:Y\n{tags}#BPM:100\n#GAP:0\n: 0 1 0 La\n"
    (folder / txt).write_bytes(body.replace("\n", newline).encode(encoding))


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, timeout=30, cwd=cwd
    )


def test_script_exists_and_is_executable():
    assert SCRIPT.is_file()
    assert SCRIPT.stat().st_mode & 0o111


def test_renames_a_case_only_mismatch_to_the_tags_spelling(tmp_path):
    folder = tmp_path / "ABBA - I Have A Dream"
    _song(folder, "song.txt", "#MP3:ABBA - I Have A Dream.mp3\n#VIDEO:ABBA - I Have A Dream.mp4\n")
    (folder / "abba - i have a dream.mp3").write_bytes(b"audio")
    (folder / "abba - i have a dream.mp4").write_bytes(b"video")

    result = _run("--root", str(tmp_path))
    assert result.returncode == 0, result.stderr
    names = set(p.name for p in folder.iterdir())
    assert "ABBA - I Have A Dream.mp3" in names
    assert "ABBA - I Have A Dream.mp4" in names
    assert "abba - i have a dream.mp3" not in names
    assert (folder / "ABBA - I Have A Dream.mp3").read_bytes() == b"audio"
    assert "Renamed 2" in result.stdout


def test_txt_file_itself_is_left_untouched(tmp_path):
    folder = tmp_path / "A - B"
    _song(folder, "song.txt", "#MP3:Song.mp3\n")
    (folder / "song.mp3").write_bytes(b"a")
    before = (folder / "song.txt").read_bytes()
    _run("--root", str(tmp_path))
    assert (folder / "song.txt").read_bytes() == before


def test_dry_run_renames_nothing(tmp_path):
    folder = tmp_path / "A - B"
    _song(folder, "song.txt", "#MP3:Song.mp3\n")
    (folder / "song.mp3").write_bytes(b"a")

    result = _run("--dry-run", "--root", str(tmp_path))
    assert result.returncode == 0, result.stderr
    assert (folder / "song.mp3").exists()
    assert not any(p.name == "Song.mp3" for p in folder.iterdir())
    assert "would rename" in result.stdout
    assert "Dry run: would rename 1" in result.stdout


def test_correct_and_truly_missing_references_are_left_alone(tmp_path):
    folder = tmp_path / "A - B"
    _song(folder, "song.txt", "#MP3:Song.mp3\n#VIDEO:Gone.mp4\n#COVER:Other [CO].jpg\n")
    (folder / "Song.mp3").write_bytes(b"a")  # exact match
    (folder / "something else.mp4").write_bytes(b"v")  # not a case variant of Gone.mp4

    result = _run("--root", str(tmp_path))
    assert result.returncode == 0, result.stderr
    assert sorted(p.name for p in folder.iterdir()) == ["Song.mp3", "something else.mp4", "song.txt"]
    assert "Renamed 0" in result.stdout


def test_non_song_txt_files_are_ignored(tmp_path):
    folder = tmp_path / "A - B"
    folder.mkdir()
    (folder / "readme.txt").write_text("#MP3:Song.mp3\njust notes\n", encoding="utf-8")
    (folder / "song.mp3").write_bytes(b"a")
    _run("--root", str(tmp_path))
    assert (folder / "song.mp3").exists()


def test_handles_crlf_and_cp1252_song_files(tmp_path):
    folder = tmp_path / "Mötley Crüe - Kickstart"
    _song(folder, "song.txt", "#MP3:Mötley Crüe - Kickstart.mp3\n", encoding="cp1252", newline="\r\n")
    (folder / "mötley crüe - kickstart.mp3").write_bytes(b"a")

    result = _run("--root", str(tmp_path))
    assert result.returncode == 0, result.stderr
    assert (folder / "Mötley Crüe - Kickstart.mp3").exists()


def test_all_media_and_image_tags_are_covered(tmp_path):
    folder = tmp_path / "A - B"
    _song(
        folder, "song.txt",
        "#AUDIO:Song.ogg\n#MP3:Song.mp3\n#VIDEO:Song.mp4\n#COVER:Song [CO].jpg\n#BACKGROUND:Song [BG].jpg\n",
    )
    for name in ("song.ogg", "song.mp3", "song.mp4", "song [co].jpg", "song [bg].jpg"):
        (folder / name).write_bytes(b"x")

    _run("--root", str(tmp_path))
    names = {p.name for p in folder.iterdir()}
    assert {"Song.ogg", "Song.mp3", "Song.mp4", "Song [CO].jpg", "Song [BG].jpg"} <= names


def test_same_file_referenced_twice_with_the_same_spelling_is_renamed_once(tmp_path):
    folder = tmp_path / "A - B"
    _song(folder, "solo.txt", "#MP3:Song.mp3\n")
    _song(folder, "duet.txt", "#MP3:Song.mp3\n#P1:A\n#P2:B\n")
    (folder / "song.mp3").write_bytes(b"a")

    result = _run("--root", str(tmp_path))
    assert result.returncode == 0, result.stderr
    assert (folder / "Song.mp3").exists()
    assert "Renamed 1" in result.stdout


def test_conflicting_spellings_for_one_file_are_skipped(tmp_path):
    folder = tmp_path / "A - B"
    _song(folder, "one.txt", "#MP3:Song.mp3\n")
    _song(folder, "two.txt", "#MP3:SONG.mp3\n")
    (folder / "song.mp3").write_bytes(b"a")

    result = _run("--root", str(tmp_path))
    assert result.returncode == 0, result.stderr
    assert (folder / "song.mp3").exists()
    assert "conflict" in result.stderr.lower()


def test_ambiguous_case_variants_on_disk_are_skipped(tmp_path):
    # possible on the NAS's own case-sensitive disk: two files differing only
    # in case - there's no telling which one the tag means.
    folder = tmp_path / "A - B"
    _song(folder, "song.txt", "#MP3:Song.mp3\n")
    (folder / "song.mp3").write_bytes(b"a")
    (folder / "SONG.mp3").write_bytes(b"b")

    result = _run("--root", str(tmp_path))
    assert result.returncode == 0, result.stderr
    assert sorted(p.name for p in folder.iterdir()) == ["SONG.mp3", "song.mp3", "song.txt"]
    assert "ambiguous" in result.stderr.lower()


def test_references_into_subfolders_are_skipped(tmp_path):
    folder = tmp_path / "A - B"
    _song(folder, "song.txt", "#MP3:sub/Song.mp3\n")
    (folder / "sub").mkdir()
    (folder / "sub" / "song.mp3").write_bytes(b"a")
    _run("--root", str(tmp_path))
    assert (folder / "sub" / "song.mp3").exists()


def test_hidden_and_synology_folders_are_skipped(tmp_path):
    for name in (".hidden", "@eaDir", "#recycle"):
        _song(tmp_path / name, "song.txt", "#MP3:Song.mp3\n")
        (tmp_path / name / "song.mp3").write_bytes(b"a")
    _run("--root", str(tmp_path))
    for name in (".hidden", "@eaDir", "#recycle"):
        assert (tmp_path / name / "song.mp3").exists()


def test_existing_leftover_temp_name_is_never_overwritten(tmp_path):
    folder = tmp_path / "A - B"
    _song(folder, "song.txt", "#MP3:Song.mp3\n")
    (folder / "song.mp3").write_bytes(b"a")
    (folder / "song.mp3.casefix-tmp").write_bytes(b"leftover")

    result = _run("--root", str(tmp_path))
    assert result.returncode == 0, result.stderr
    assert (folder / "song.mp3").read_bytes() == b"a"
    assert (folder / "song.mp3.casefix-tmp").read_bytes() == b"leftover"
    assert "skip" in result.stderr.lower()


def test_default_root_is_the_current_directory(tmp_path):
    folder = tmp_path / "A - B"
    _song(folder, "song.txt", "#MP3:Song.mp3\n")
    (folder / "song.mp3").write_bytes(b"a")
    result = _run(cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert (folder / "Song.mp3").exists()


def test_root_that_is_not_a_directory_fails_cleanly(tmp_path):
    result = _run("--root", str(tmp_path / "nope"))
    assert result.returncode != 0
    assert "not a directory" in result.stderr
