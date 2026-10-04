"""Tests for scripts/apply_moves.sh: the standalone bash companion to the
admin integrity view's move-list exports (app/move_export.py) - run by
hand directly against the real library on its host, never shipped in the
container (the Dockerfile only COPYs app/, not scripts/). Builds its own
NUL-delimited move-list files directly, the same root-relative-path format
app/move_export.py produces, and actually invokes the real script via
subprocess against a throwaway tmp_path tree standing in for that library.
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


def _run(*args: str, cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT), *args], capture_output=True, text=True, timeout=10, cwd=cwd
    )


def test_script_exists_and_is_executable():
    assert SCRIPT.is_file()
    assert SCRIPT.stat().st_mode & 0o111  # at least one executable bit


def test_moves_a_file_into_a_new_destination_folder(tmp_path):
    (tmp_path / "src.txt").write_text("hello")
    move_list = tmp_path / "moves.list"
    move_list.write_bytes(_move_list([("src.txt", "newfolder/dst.txt")]))

    result = _run("--root", str(tmp_path), str(move_list))
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "src.txt").exists()
    assert (tmp_path / "newfolder" / "dst.txt").read_text() == "hello"


def test_root_with_a_trailing_slash_behaves_the_same_as_without(tmp_path):
    (tmp_path / "src.txt").write_text("hello")
    move_list = tmp_path / "moves.list"
    move_list.write_bytes(_move_list([("src.txt", "newfolder/dst.txt")]))

    result = _run("--root", str(tmp_path) + "/", str(move_list))
    assert result.returncode == 0, result.stderr
    assert "//" not in result.stdout
    assert not (tmp_path / "src.txt").exists()
    assert (tmp_path / "newfolder" / "dst.txt").read_text() == "hello"


def test_root_of_just_a_slash_is_not_stripped_to_nothing(tmp_path):
    # a trailing-slash strip must not turn root "/" into an empty string,
    # which would silently change every path's meaning.
    move_list = tmp_path / "moves.list"
    move_list.write_bytes(_move_list([("does-not-exist-at-the-real-root.txt", "dst.txt")]))

    result = _run("--dry-run", "--root", "/", str(move_list))
    assert result.returncode == 0, result.stderr
    assert "skip (source missing): //does-not-exist" not in result.stderr
    assert "skip (source missing): /does-not-exist" in result.stderr


def test_default_root_is_the_current_directory(tmp_path):
    # the documented default workflow: run from inside the real library
    # root, with no --root needed (app/move_export.py's paths are relative
    # to exactly that root).
    (tmp_path / "src.txt").write_text("hello")
    move_list = tmp_path / "moves.list"
    move_list.write_bytes(_move_list([("src.txt", "dst.txt")]))

    result = _run(str(move_list), cwd=str(tmp_path))
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "dst.txt").read_text() == "hello"


def test_root_can_differ_from_the_move_lists_own_directory(tmp_path):
    # the move-list file itself can live anywhere - only --root matters for
    # resolving the relative paths inside it.
    library = tmp_path / "library"
    library.mkdir()
    (library / "src.txt").write_text("hello")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    move_list = elsewhere / "moves.list"
    move_list.write_bytes(_move_list([("src.txt", "dst.txt")]))

    result = _run("--root", str(library), str(move_list))
    assert result.returncode == 0, result.stderr
    assert (library / "dst.txt").read_text() == "hello"


def test_handles_filenames_with_special_characters(tmp_path):
    name = "weird's \"name\" (ft. someone).txt"
    (tmp_path / name).write_text("x")
    move_list = tmp_path / "moves.list"
    move_list.write_bytes(_move_list([(name, f"dest's folder/{name}")]))

    result = _run("--root", str(tmp_path), str(move_list))
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "dest's folder" / name).exists()


def test_dry_run_does_not_move_anything(tmp_path):
    (tmp_path / "src.txt").write_text("hello")
    move_list = tmp_path / "moves.list"
    move_list.write_bytes(_move_list([("src.txt", "newfolder/dst.txt")]))

    result = _run("--dry-run", "--root", str(tmp_path), str(move_list))
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "src.txt").exists()
    assert not (tmp_path / "newfolder" / "dst.txt").exists()


def test_skips_when_destination_already_exists(tmp_path):
    (tmp_path / "src.txt").write_text("hello")
    (tmp_path / "dst.txt").write_text("already here")
    move_list = tmp_path / "moves.list"
    move_list.write_bytes(_move_list([("src.txt", "dst.txt")]))

    result = _run("--root", str(tmp_path), str(move_list))
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "src.txt").exists()  # not moved
    assert (tmp_path / "dst.txt").read_text() == "already here"  # not overwritten
    assert "skip" in result.stderr.lower()


def test_skips_when_source_is_missing(tmp_path):
    move_list = tmp_path / "moves.list"
    move_list.write_bytes(_move_list([("does-not-exist.txt", "dst.txt")]))

    result = _run("--root", str(tmp_path), str(move_list))
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "dst.txt").exists()
    assert "missing" in result.stderr.lower() or "skip" in result.stderr.lower()


def test_moves_several_pairs_from_one_file(tmp_path):
    pairs = []
    for i in range(3):
        (tmp_path / f"src{i}.txt").write_text(str(i))
        pairs.append((f"src{i}.txt", f"out/dst{i}.txt"))
    move_list = tmp_path / "moves.list"
    move_list.write_bytes(_move_list(pairs))

    result = _run("--root", str(tmp_path), str(move_list))
    assert result.returncode == 0, result.stderr
    for i in range(3):
        assert (tmp_path / "out" / f"dst{i}.txt").read_text() == str(i)


def test_fails_cleanly_with_no_arguments():
    result = _run()
    assert result.returncode != 0


def test_fails_cleanly_when_file_does_not_exist(tmp_path):
    result = _run("--root", str(tmp_path), str(tmp_path / "nope.list"))
    assert result.returncode != 0
