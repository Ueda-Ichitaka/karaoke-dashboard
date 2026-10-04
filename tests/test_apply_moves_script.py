"""Tests for scripts/apply_moves.sh: the standalone bash companion to the
admin integrity view's move-list exports (app/move_export.py) - run by
hand against the real songs_dir, never shipped in the container (the
Dockerfile only COPYs app/, not scripts/). Builds its own NUL-delimited
move-list files directly, the same format app/move_export.py produces, and
actually invokes the real script via subprocess against a throwaway
tmp_path tree.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "apply_moves.sh"


def _move_list(pairs: list[tuple[str, str]]) -> bytes:
    data = b""
    for src, dst in pairs:
        data += src.encode("utf-8") + b"\x00" + dst.encode("utf-8") + b"\x00"
    return data


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT), *args], capture_output=True, text=True, timeout=10
    )


def test_script_exists_and_is_executable():
    assert SCRIPT.is_file()
    assert SCRIPT.stat().st_mode & 0o111  # at least one executable bit


def test_moves_a_file_into_a_new_destination_folder(tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("hello")
    dst = tmp_path / "newfolder" / "dst.txt"
    move_list = tmp_path / "moves.list"
    move_list.write_bytes(_move_list([(str(src), str(dst))]))

    result = _run(str(move_list))
    assert result.returncode == 0, result.stderr
    assert not src.exists()
    assert dst.read_text() == "hello"


def test_handles_filenames_with_special_characters(tmp_path):
    src = tmp_path / "weird's \"name\" (ft. someone).txt"
    src.write_text("x")
    dst = tmp_path / "dest's folder" / "weird's \"name\" (ft. someone).txt"
    move_list = tmp_path / "moves.list"
    move_list.write_bytes(_move_list([(str(src), str(dst))]))

    result = _run(str(move_list))
    assert result.returncode == 0, result.stderr
    assert dst.exists()


def test_dry_run_does_not_move_anything(tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("hello")
    dst = tmp_path / "newfolder" / "dst.txt"
    move_list = tmp_path / "moves.list"
    move_list.write_bytes(_move_list([(str(src), str(dst))]))

    result = _run("--dry-run", str(move_list))
    assert result.returncode == 0, result.stderr
    assert src.exists()
    assert not dst.exists()


def test_skips_when_destination_already_exists(tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("hello")
    dst = tmp_path / "dst.txt"
    dst.write_text("already here")
    move_list = tmp_path / "moves.list"
    move_list.write_bytes(_move_list([(str(src), str(dst))]))

    result = _run(str(move_list))
    assert result.returncode == 0, result.stderr
    assert src.exists()  # not moved
    assert dst.read_text() == "already here"  # not overwritten
    assert "skip" in result.stderr.lower()


def test_skips_when_source_is_missing(tmp_path):
    src = tmp_path / "does-not-exist.txt"
    dst = tmp_path / "dst.txt"
    move_list = tmp_path / "moves.list"
    move_list.write_bytes(_move_list([(str(src), str(dst))]))

    result = _run(str(move_list))
    assert result.returncode == 0, result.stderr
    assert not dst.exists()
    assert "missing" in result.stderr.lower() or "skip" in result.stderr.lower()


def test_moves_several_pairs_from_one_file(tmp_path):
    pairs = []
    for i in range(3):
        src = tmp_path / f"src{i}.txt"
        src.write_text(str(i))
        dst = tmp_path / "out" / f"dst{i}.txt"
        pairs.append((str(src), str(dst)))
    move_list = tmp_path / "moves.list"
    move_list.write_bytes(_move_list(pairs))

    result = _run(str(move_list))
    assert result.returncode == 0, result.stderr
    for i in range(3):
        assert (tmp_path / "out" / f"dst{i}.txt").read_text() == str(i)


def test_fails_cleanly_with_no_arguments():
    result = _run()
    assert result.returncode != 0


def test_fails_cleanly_when_file_does_not_exist(tmp_path):
    result = _run(str(tmp_path / "nope.list"))
    assert result.returncode != 0
