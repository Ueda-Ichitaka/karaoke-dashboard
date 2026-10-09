"""Tests for scripts/repair_library.py: the standalone, one-off library repair
for songs whose .txt lacks a working audio/video source, run against a
throwaway tmp_path library via subprocess (plus its pure mapping helpers
imported directly).

Groups (see the script's own header): A - a duet timed like its solo sibling
gets the solo's media tags; B - any other duet with a solo sibling moves to
its own "<folder> [DUET]" folder with copies of the solo's media and a
report row; C - a missing/dangling tag is linked to the one identifiable
file; D - nothing to link, so a report row. Report rows go to a CSV in the
dashboard's broken.csv format, for its "Import CSV".
"""

from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from app.genres import GENRE_CHOICES
from app.languages import LANGUAGE_CHOICES
from app.report_import import COLUMNS

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "repair_library.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("repair_library", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look their module up here
    spec.loader.exec_module(module)
    return module


def _song(folder: Path, name: str, tags: str, encoding="utf-8", newline="\n", bpm="200", gap="1000") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    body = f"#TITLE:Song\n#ARTIST:Band\n{tags}#BPM:{bpm}\n#GAP:{gap}\n: 0 4 0 La\nE\n"
    path = folder / name
    path.write_bytes(body.replace("\n", newline).encode(encoding))
    return path


def _usdb(folder: Path, txt_name: str, video_id: str = "", cover: str = "") -> None:
    meta = f"v={video_id}" if video_id else ""
    data = {
        "song_id": 1, "meta_tags": meta, "txt": {"fname": txt_name},
        "cover": {"fname": "c.jpg", "resource": cover} if cover else None,
    }
    (folder / f"{txt_name}.usdb").write_text(json.dumps(data))


def _tags(path: Path) -> dict[str, str]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    tags = {}
    for line in text.splitlines():
        if not line.startswith("#"):
            break
        key, _, value = line[1:].partition(":")
        tags[key.upper()] = value
    return tags


def _run(root: Path, *args: str, csv_path: Path | None = None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(SCRIPT), "--root", str(root), *args]
    if csv_path is not None:
        cmd += ["--csv", str(csv_path)]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60)


def _rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _snapshot(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


# ------------------------------------------------------------------- basics
def test_script_exists_and_is_executable():
    assert SCRIPT.is_file()
    assert SCRIPT.stat().st_mode & 0o111


def test_root_that_is_not_a_directory_fails_cleanly(tmp_path):
    result = _run(tmp_path / "nope")
    assert result.returncode != 0
    assert "not a directory" in result.stderr


def test_csv_has_the_dashboards_broken_csv_header(tmp_path):
    lib = tmp_path / "songs"
    _song(lib / "Band - Song", "song.txt", "")
    out = tmp_path / "out.csv"
    _run(lib, csv_path=out)
    assert out.read_text(encoding="utf-8").splitlines()[0] == ",".join(COLUMNS)


# ------------------------------------------------------- C: link a present file
def test_missing_audio_tag_is_set_to_the_only_audio_file(tmp_path):
    lib = tmp_path / "songs"
    txt = _song(lib / "Band - Song", "song.txt", "")
    (lib / "Band - Song" / "Band - Song.mp3").write_bytes(b"a")
    result = _run(lib, csv_path=tmp_path / "out.csv")
    assert result.returncode == 0, result.stderr
    assert _tags(txt)["MP3"] == "Band - Song.mp3"
    assert _rows(tmp_path / "out.csv") == []


def test_dangling_tags_are_relinked_to_the_present_files(tmp_path):
    lib = tmp_path / "songs"
    folder = lib / "Accept - The King"
    txt = _song(folder, "song.txt", "#MP3:Accept - The King.mp3\n#VIDEO:Accept - The King.mp4\n")
    (folder / "Accept - The King [Lyrics] [int0HgPZ768].mp3").write_bytes(b"a")
    (folder / "Accept - The King [Lyrics] [int0HgPZ768].mp4").write_bytes(b"v")
    _run(lib, csv_path=tmp_path / "out.csv")
    tags = _tags(txt)
    assert tags["MP3"] == "Accept - The King [Lyrics] [int0HgPZ768].mp3"
    assert tags["VIDEO"] == "Accept - The King [Lyrics] [int0HgPZ768].mp4"


def test_missing_video_tag_is_added_when_a_video_file_is_present(tmp_path):
    lib = tmp_path / "songs"
    txt = _song(lib / "Band - Song", "song.txt", "#MP3:a.mp3\n")
    (lib / "Band - Song" / "a.mp3").write_bytes(b"a")
    (lib / "Band - Song" / "clip.mp4").write_bytes(b"v")
    _run(lib, csv_path=tmp_path / "out.csv")
    assert _tags(txt)["VIDEO"] == "clip.mp4"


def test_audio_only_song_without_video_tag_or_file_is_fine(tmp_path):
    lib = tmp_path / "songs"
    txt = _song(lib / "Band - Song", "song.txt", "#MP3:a.mp3\n")
    (lib / "Band - Song" / "a.mp3").write_bytes(b"a")
    before = txt.read_bytes()
    _run(lib, csv_path=tmp_path / "out.csv")
    assert txt.read_bytes() == before
    assert _rows(tmp_path / "out.csv") == []


def test_several_audio_files_pick_the_one_with_the_usdb_video_id(tmp_path):
    lib = tmp_path / "songs"
    folder = lib / "Band - Song"
    txt = _song(folder, "song.txt", "")
    _usdb(folder, "song.txt", video_id="16y1AkoZkmQ")
    (folder / "Song (Official Audio) [Nl_Eo2QzqU4].mp3").write_bytes(b"a")
    (folder / "Song (Sopot Festival 1979) [16y1AkoZkmQ].mp3").write_bytes(b"b")
    _run(lib, csv_path=tmp_path / "out.csv")
    assert _tags(txt)["MP3"] == "Song (Sopot Festival 1979) [16y1AkoZkmQ].mp3"


def test_several_audio_files_without_an_id_match_become_a_report(tmp_path):
    lib = tmp_path / "songs"
    folder = lib / "Band - Song"
    txt = _song(folder, "song.txt", "")
    (folder / "one.mp3").write_bytes(b"a")
    (folder / "two.mp3").write_bytes(b"b")
    before = txt.read_bytes()
    _run(lib, csv_path=tmp_path / "out.csv")
    assert txt.read_bytes() == before
    [row] = _rows(tmp_path / "out.csv")
    assert (row["band"], row["song name"], row["category"]) == ("Band", "Song", "audio")
    assert "Several audio files" in row["description"]


def test_case_only_mismatch_is_left_to_the_case_fixer(tmp_path):
    lib = tmp_path / "songs"
    folder = lib / "Band - Song"
    txt = _song(folder, "song.txt", "#MP3:Song.mp3\n")
    (folder / "song.mp3").write_bytes(b"a")
    before = txt.read_bytes()
    result = _run(lib, csv_path=tmp_path / "out.csv")
    assert txt.read_bytes() == before
    assert "fix_case_mismatches.py" in result.stderr


def test_linked_underscore_file_loses_its_leading_underscore(tmp_path):
    lib = tmp_path / "songs"
    folder = lib / "Survivor - Eye Of The Tiger"
    txt = _song(folder, "song.txt", "#MP3:a.mp3\n#VIDEO:gone.mp4\n")
    (folder / "a.mp3").write_bytes(b"a")
    (folder / "_Survivor - Eye Of The Tiger.mp4").write_bytes(b"v")
    _run(lib, csv_path=tmp_path / "out.csv")
    assert (folder / "Survivor - Eye Of The Tiger.mp4").read_bytes() == b"v"
    assert not (folder / "_Survivor - Eye Of The Tiger.mp4").exists()
    assert _tags(txt)["VIDEO"] == "Survivor - Eye Of The Tiger.mp4"


def test_underscore_file_keeps_its_name_when_the_plain_name_is_taken(tmp_path):
    # the share ignores letter case, so a name differing only in case clashes too
    lib = tmp_path / "songs"
    folder = lib / "Band - Song"
    txt = _song(folder, "song.txt", "#MP3:a.mp3\n#VIDEO:gone.mp4\n")
    _usdb(folder, "song.txt", video_id="AbCdEfGhIjK")
    (folder / "a.mp3").write_bytes(b"a")
    (folder / "_Band - Song [AbCdEfGhIjK].mp4").write_bytes(b"v")
    (folder / "band - song [abcdefghijk].MP4").write_bytes(b"other")
    _run(lib, csv_path=tmp_path / "out.csv")
    assert (folder / "_Band - Song [AbCdEfGhIjK].mp4").read_bytes() == b"v"
    assert (folder / "band - song [abcdefghijk].MP4").read_bytes() == b"other"
    assert _tags(txt)["VIDEO"] == "_Band - Song [AbCdEfGhIjK].mp4"


# ----------------------------------------------- editing a .txt preserves it
def test_edit_keeps_encoding_line_endings_and_makes_a_backup(tmp_path):
    lib = tmp_path / "songs"
    folder = lib / "Mötley Crüe - Kickstart"
    txt = _song(folder, "song.txt", "#ARTIST:Mötley Crüe\n", encoding="cp1252", newline="\r\n")
    original = txt.read_bytes()
    (folder / "kickstart.mp3").write_bytes(b"a")
    _run(lib, csv_path=tmp_path / "out.csv")

    new = txt.read_bytes()
    assert b"#MP3:kickstart.mp3\r\n#BPM:" in new  # inserted right before #BPM
    assert "Mötley".encode("cp1252") in new
    assert new.count(b"\r\n") == original.count(b"\r\n") + 1
    assert (folder / "song.txt.bak").read_bytes() == original


def test_existing_backup_is_never_overwritten(tmp_path):
    lib = tmp_path / "songs"
    folder = lib / "Band - Song"
    _song(folder, "song.txt", "")
    (folder / "song.txt.bak").write_bytes(b"oldest original")
    (folder / "a.mp3").write_bytes(b"a")
    _run(lib, csv_path=tmp_path / "out.csv")
    assert (folder / "song.txt.bak").read_bytes() == b"oldest original"


# ------------------------------------------- A: duet timed like the solo
def test_duet_timed_like_its_solo_gets_the_solos_media_tags(tmp_path):
    lib = tmp_path / "songs"
    folder = lib / "Band - Song"
    _song(folder, "solo.txt", "#MP3:Band - Song.mp3\n#VIDEO:Band - Song.mp4\n", gap="1000")
    duet = _song(folder, "duet.txt", "#P1:A\n#P2:B\n", gap="1600")  # 0.6 s apart: still group A
    (folder / "Band - Song.mp3").write_bytes(b"a")
    (folder / "Band - Song.mp4").write_bytes(b"v")
    _run(lib, csv_path=tmp_path / "out.csv")
    tags = _tags(duet)
    assert tags["MP3"] == "Band - Song.mp3"
    assert tags["VIDEO"] == "Band - Song.mp4"
    assert tags["GAP"] == "1600"  # keeps its own #GAP
    assert not (lib / "Band - Song [DUET]").exists()
    assert _rows(tmp_path / "out.csv") == []


def test_duet_with_a_bpm_within_a_tenth_of_a_percent_counts_as_the_same_recording(tmp_path):
    lib = tmp_path / "songs"
    folder = lib / "The Black Eyed Peas - Shut Up"
    _song(folder, "solo.txt", "#MP3:a.mp3\n", bpm="225.9", gap="20920")
    duet = _song(folder, "duet.txt", "#P1:A\n#P2:B\n", bpm="226", gap="20920")  # 0.044% apart
    (folder / "a.mp3").write_bytes(b"a")
    _run(lib, csv_path=tmp_path / "out.csv")
    assert _tags(duet)["MP3"] == "a.mp3"
    assert not (lib / "The Black Eyed Peas - Shut Up [DUET]").exists()


def test_duet_with_a_bpm_more_than_a_tenth_of_a_percent_off_moves(tmp_path):
    lib = tmp_path / "songs"
    folder = lib / "Band - Song"
    _song(folder, "solo.txt", "#MP3:a.mp3\n", bpm="200")
    _song(folder, "duet.txt", "#P1:A\n#P2:B\n", bpm="200.4")  # 0.2% apart
    (folder / "a.mp3").write_bytes(b"a")
    _run(lib, csv_path=tmp_path / "out.csv")
    assert (lib / "Band - Song [DUET]" / "duet.txt").is_file()


# --------------------------------------- B: duet that needs re-timing moves
def _rasputin(lib: Path, duet_gap="49930", duet_bpm="254.7") -> Path:
    folder = lib / "Boney M. - Rasputin"
    _song(folder, "Boney M. - Rasputin.txt", "#MP3:Boney M. - Rasputin.mp3\n#VIDEO:Boney M. - Rasputin.mp4\n",
          bpm="253.45", gap="56220")
    _song(
        folder, "Boney M. - Rasputin [DUET].txt",
        "#LANGUAGE:English\n#GENRE:Disco, Pop\n#COVER:Boney M. - Rasputin [DUET] [CO].jpg\n#P1:Lead\n#P2:Backing\n",
        bpm=duet_bpm, gap=duet_gap,
    )
    _usdb(folder, "Boney M. - Rasputin [DUET].txt", video_id="vIjdhIErp8I", cover="https://img.example/c.jpg")
    (folder / "Boney M. - Rasputin.mp3").write_bytes(b"audio")
    (folder / "Boney M. - Rasputin.mp4").write_bytes(b"video")
    (folder / "Boney M. - Rasputin [DUET] [CO].jpg").write_bytes(b"cover")
    return folder


def test_duet_with_different_timing_moves_to_its_own_folder_with_media_copies(tmp_path):
    lib = tmp_path / "songs"
    folder = _rasputin(lib)
    result = _run(lib, csv_path=tmp_path / "out.csv")
    assert result.returncode == 0, result.stderr

    dest = lib / "Boney M. - Rasputin [DUET]"
    duet = dest / "Boney M. - Rasputin [DUET].txt"
    assert duet.is_file()
    assert not (folder / "Boney M. - Rasputin [DUET].txt").exists()
    assert (dest / "Boney M. - Rasputin [DUET].txt.usdb").is_file()  # its USDB marker moves along
    assert (dest / "Boney M. - Rasputin [DUET] [CO].jpg").read_bytes() == b"cover"  # its own cover moves
    assert (dest / "Boney M. - Rasputin.mp3").read_bytes() == b"audio"  # media is copied...
    assert (dest / "Boney M. - Rasputin.mp4").read_bytes() == b"video"
    assert (folder / "Boney M. - Rasputin.mp3").read_bytes() == b"audio"  # ...the solo keeps its own
    assert (folder / "Boney M. - Rasputin.mp4").is_file()
    tags = _tags(duet)
    assert tags["MP3"] == "Boney M. - Rasputin.mp3"
    assert tags["VIDEO"] == "Boney M. - Rasputin.mp4"
    assert tags["GAP"] == "49930"


def test_moved_duet_gets_a_report_row_with_everything_the_files_state(tmp_path):
    lib = tmp_path / "songs"
    _rasputin(lib)
    _run(lib, csv_path=tmp_path / "out.csv")
    [row] = _rows(tmp_path / "out.csv")
    assert row["band"] == "Boney M."
    assert row["song name"] == "Rasputin [DUET]"
    assert row["category"] == "other"
    assert row["language"] == "en"
    assert row["cover_url"] == "https://img.example/c.jpg"
    assert row["genre"] == "pop"  # "Disco" isn't a dashboard genre
    assert row["trait"] == "none"
    assert row["lyrics_url"] == ""
    description = row["description"]
    assert "re-timed" in description and "#GAP" in description
    assert "254.7" in description and "253.45" in description
    assert "https://www.youtube.com/watch?v=vIjdhIErp8I" in description
    for char in ",;\"":
        assert char not in description  # the importer would strip these


def test_gap_just_over_the_limit_moves_the_duet(tmp_path):
    lib = tmp_path / "songs"
    folder = lib / "Band - Song"
    _song(folder, "solo.txt", "#MP3:a.mp3\n", gap="1000")
    _song(folder, "duet.txt", "#P1:A\n#P2:B\n", gap="1601")
    (folder / "a.mp3").write_bytes(b"a")
    _run(lib, csv_path=tmp_path / "out.csv")
    assert (lib / "Band - Song [DUET]" / "duet.txt").is_file()


def test_duet_is_not_moved_when_the_destination_folder_exists(tmp_path):
    lib = tmp_path / "songs"
    folder = _rasputin(lib)
    (lib / "Boney M. - Rasputin [DUET]").mkdir()
    result = _run(lib, csv_path=tmp_path / "out.csv")
    assert (folder / "Boney M. - Rasputin [DUET].txt").is_file()
    assert "already exists" in result.stderr


def test_duet_whose_intended_video_is_in_the_folder_is_linked_not_moved(tmp_path):
    lib = tmp_path / "songs"
    folder = _rasputin(lib)
    (folder / "Boney M. - Rasputin [vIjdhIErp8I].mp4").write_bytes(b"v")
    (folder / "Boney M. - Rasputin [vIjdhIErp8I].mp3").write_bytes(b"a")
    _run(lib, csv_path=tmp_path / "out.csv")
    tags = _tags(folder / "Boney M. - Rasputin [DUET].txt")
    assert tags["MP3"] == "Boney M. - Rasputin [vIjdhIErp8I].mp3"
    assert tags["VIDEO"] == "Boney M. - Rasputin [vIjdhIErp8I].mp4"
    assert not (lib / "Boney M. - Rasputin [DUET]").exists()


# -------------------------------------------------- D: nothing to link
def test_no_audio_file_at_all_becomes_an_audio_report(tmp_path):
    lib = tmp_path / "songs"
    folder = lib / "Slipknot - XIX"
    _song(folder, "song.txt", "#MP3:Slipknot - Xix.mp3\n#LANGUAGE:English\n")
    _run(lib, csv_path=tmp_path / "out.csv")
    [row] = _rows(tmp_path / "out.csv")
    assert (row["band"], row["song name"], row["category"], row["language"]) == ("Slipknot", "XIX", "audio", "en")
    assert "Slipknot - Xix.mp3" in row["description"]


def test_dangling_video_with_no_video_file_becomes_a_video_report(tmp_path):
    lib = tmp_path / "songs"
    folder = lib / "Band - Song"
    _song(folder, "song.txt", "#MP3:a.mp3\n#VIDEO:gone.mp4\n")
    (folder / "a.mp3").write_bytes(b"a")
    _run(lib, csv_path=tmp_path / "out.csv")
    [row] = _rows(tmp_path / "out.csv")
    assert row["category"] == "video"
    assert "gone.mp4" in row["description"]


def test_a_song_gets_one_row_with_every_other_repair_in_its_description(tmp_path):
    # the dashboard reports a song only once: the first row keeps its
    # category, any further repairs for the same song go into its description
    lib = tmp_path / "songs"
    folder = lib / "Ulver - Eos"
    _song(folder, "song.txt", "#VIDEO:Ulver - Eos.mp4\n#LANGUAGE:English\n")
    _song(folder, "other.txt", "#MP3:gone.mp3\n")
    _usdb(folder, "other.txt", cover="https://img.example/c.jpg")
    _run(lib, csv_path=tmp_path / "out.csv")
    [row] = _rows(tmp_path / "out.csv")
    assert row["category"] == "audio"
    description = row["description"]
    assert description.count("No audio file") == 2
    assert "Also (video): No video file in the folder for song.txt" in description
    # the first row (other.txt) states no language - a later row fills that blank
    assert row["language"] == "en"
    assert row["cover_url"] == "https://img.example/c.jpg"
    for char in ",;\"|":
        assert char not in description


# ------------------------------------------------------------- dry run etc.
def test_dry_run_changes_nothing_and_writes_no_csv_by_default(tmp_path):
    lib = tmp_path / "songs"
    _rasputin(lib)
    _song(lib / "Band - Song", "song.txt", "")
    (lib / "Band - Song" / "a.mp3").write_bytes(b"a")
    before = _snapshot(lib)

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--dry-run", "--root", str(lib)],
        capture_output=True, text=True, timeout=60, cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert _snapshot(lib) == before
    assert list(tmp_path.glob("*.csv")) == []
    assert "would move" in result.stdout
    assert "would set #MP3" in result.stdout
    assert "would move 1 duets" in result.stdout.splitlines()[-1]


def test_dry_run_with_explicit_csv_previews_the_rows(tmp_path):
    lib = tmp_path / "songs"
    _rasputin(lib)
    before = _snapshot(lib)
    _run(lib, "--dry-run", csv_path=tmp_path / "preview.csv")
    assert _snapshot(lib) == before
    [row] = _rows(tmp_path / "preview.csv")
    assert row["song name"] == "Rasputin [DUET]"


def test_non_song_txt_and_system_folders_are_ignored(tmp_path):
    lib = tmp_path / "songs"
    (lib / "Band - Song").mkdir(parents=True)
    (lib / "Band - Song" / "readme.txt").write_text("#MP3:x.mp3\nnotes\n")
    (lib / "Band - Song" / "a.mp3").write_bytes(b"a")
    for name in (".hidden", "@eaDir", "#recycle"):
        _song(lib / name, "song.txt", "")
        (lib / name / "a.mp3").write_bytes(b"a")
    before = _snapshot(lib)
    _run(lib, csv_path=tmp_path / "out.csv")
    assert _snapshot(lib) == before


# --------------------------------------------- mapping helpers, kept in sync
def test_language_mapping_matches_the_dashboards_list():
    script = _load_script()
    for code, label in LANGUAGE_CHOICES:
        if code and code != "mixed":
            assert script.map_language(label) == code


def test_language_mapping_handles_the_librarys_own_spellings():
    script = _load_script()
    assert script.map_language("Englisch") == "en"
    assert script.map_language("Deutsch") == "de"
    assert script.map_language("Español") == "es"
    assert script.map_language("Japanese (romanized)") == "ja"
    assert script.map_language("Korean (romanized), English") == "mixed"
    assert script.map_language("English, German") == "mixed"
    assert script.map_language("Somali") == ""  # not a dashboard language
    assert script.map_language("Detusch") == ""  # typo - no guessing
    assert script.map_language("") == ""


def test_genre_mapping_matches_the_dashboards_list_exactly():
    script = _load_script()
    for code, label in GENRE_CHOICES:
        if code != "default":
            assert script.map_genres(label) == code
            assert script.map_genres(code) == code
    assert script.map_genres("Pop, Electronic") == "pop"
    assert script.map_genres("Metal / Folk") == "metal,folk"
    assert script.map_genres("Power Metal") == "default"  # no guessing from parts
    assert script.map_genres("") == "default"
