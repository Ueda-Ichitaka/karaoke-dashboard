"""Tests for app/misplaced_check.py: flags a song sitting in a folder whose
name doesn't match that song's own #ARTIST/#TITLE tags - e.g. a batch-import
bug that dumped several unrelated songs' files into one "Artist - Title"
folder, of which only one actually belongs there.
"""

from __future__ import annotations

from pathlib import Path

from app import misplaced_check


def _write_song(folder: Path, filename: str, artist: str, title: str) -> None:
    (folder / filename).write_text(
        f"#TITLE:{title}\n#ARTIST:{artist}\n#BPM:120\n#GAP:0\nE\n", encoding="utf-8"
    )


def test_correctly_placed_song_is_not_flagged(tmp_path):
    folder = tmp_path / "Queen - Bohemian Rhapsody"
    folder.mkdir()
    _write_song(folder, "song.txt", "Queen", "Bohemian Rhapsody")
    assert misplaced_check.find_misplaced_songs(root=tmp_path) == []


def test_extra_unrelated_song_in_folder_is_flagged(tmp_path):
    folder = tmp_path / "30 Seconds to Mars - Attack"
    folder.mkdir()
    _write_song(folder, "Attack.txt", "30 Seconds to Mars", "Attack")
    _write_song(folder, "KingsAndQueens.txt", "30 Seconds to Mars", "Kings and Queens")
    _write_song(folder, "Unrelated.txt", "Someone Else", "Totally Different Song")

    results = misplaced_check.find_misplaced_songs(root=tmp_path)
    assert len(results) == 2
    titles = {r.title for r in results}
    assert titles == {"Kings and Queens", "Totally Different Song"}

    kq = next(r for r in results if r.title == "Kings and Queens")
    assert kq.folder == "30 Seconds to Mars - Attack"
    assert kq.source_file == "KingsAndQueens.txt"
    assert kq.artist == "30 Seconds to Mars"
    assert kq.expected_folder == "30 Seconds to Mars - Kings and Queens"


def test_folder_with_no_matching_song_flags_everything(tmp_path):
    folder = tmp_path / "AC-DC - Back In Black (Live - 1991)"
    folder.mkdir()
    _write_song(folder, "a.txt", "Other Band", "Some Song")
    _write_song(folder, "b.txt", "Other Band 2", "Some Other Song")
    results = misplaced_check.find_misplaced_songs(root=tmp_path)
    assert len(results) == 2


def test_matching_is_case_and_whitespace_insensitive(tmp_path):
    folder = tmp_path / "Queen - Bohemian Rhapsody"
    folder.mkdir()
    _write_song(folder, "song.txt", "  queen  ", "  BOHEMIAN RHAPSODY  ")
    assert misplaced_check.find_misplaced_songs(root=tmp_path) == []


def test_song_missing_artist_or_title_tag_is_skipped(tmp_path):
    folder = tmp_path / "Queen - Bohemian Rhapsody"
    folder.mkdir()
    (folder / "song.txt").write_text("#BPM:120\n#GAP:0\nE\n", encoding="utf-8")
    assert misplaced_check.find_misplaced_songs(root=tmp_path) == []


def test_non_conforming_folder_name_is_skipped_here(tmp_path):
    # a folder whose own name doesn't parse as "Artist - Title" is
    # structure_check's concern - there's nothing to compare a song against.
    folder = tmp_path / "PlainFolderNoSeparator"
    folder.mkdir()
    _write_song(folder, "song.txt", "Someone", "Something")
    assert misplaced_check.find_misplaced_songs(root=tmp_path) == []


def test_ignored_and_hidden_folders_are_skipped(tmp_path):
    (tmp_path / "@eaDir").mkdir()
    (tmp_path / ".hidden").mkdir()
    assert misplaced_check.find_misplaced_songs(root=tmp_path) == []


# ------------------------------------------------- filename-safe false positives
def test_record_label_suffix_in_folder_name_is_not_flagged(tmp_path):
    # yt-dlp/import tooling sometimes appends the record label to the
    # folder name; it's not part of the actual song title tag.
    folder = tmp_path / "Xandria - Nightfall - Napalm Records"
    folder.mkdir()
    _write_song(folder, "song.txt", "Xandria", "Nightfall")
    assert misplaced_check.find_misplaced_songs(root=tmp_path) == []


def test_parenthesized_and_bracketed_suffixes_in_tag_are_ignored(tmp_path):
    # "(Official Audio)" and a yt-dlp video-id suffix like "[aBcDeFgHiJk]"
    # in the tag's own title aren't part of the real song title either.
    folder = tmp_path / "System of a Down - Lost In Hollywood"
    folder.mkdir()
    _write_song(
        folder, "song.txt", "System of a Down",
        "Lost In Hollywood (Official Audio) [aBcDeFgHiJk]",
    )
    assert misplaced_check.find_misplaced_songs(root=tmp_path) == []


def test_colon_missing_from_folder_name_is_not_flagged(tmp_path):
    # ":" isn't allowed in filenames, so it's dropped from the folder name
    # even though the real tag keeps it.
    folder = tmp_path / "ASP - Duett Das Minnelied der Incubi"
    folder.mkdir()
    _write_song(folder, "song.txt", "ASP", "Duett: Das Minnelied der Incubi")
    assert misplaced_check.find_misplaced_songs(root=tmp_path) == []


def test_slash_in_tag_vs_hyphen_in_folder_name_is_not_flagged(tmp_path):
    # "/" isn't allowed in filenames either, so "AC/DC" becomes "AC-DC".
    folder = tmp_path / "AC-DC - Back In Black"
    folder.mkdir()
    _write_song(folder, "song.txt", "AC/DC", "Back In Black")
    assert misplaced_check.find_misplaced_songs(root=tmp_path) == []


def test_genuinely_misplaced_song_is_still_flagged_after_cleaning(tmp_path):
    # the cleanup must not make the check toothless.
    folder = tmp_path / "30 Seconds to Mars - Attack"
    folder.mkdir()
    _write_song(folder, "Attack.txt", "30 Seconds to Mars", "Attack")
    _write_song(folder, "Unrelated.txt", "Someone Else", "Totally Different Song")
    results = misplaced_check.find_misplaced_songs(root=tmp_path)
    assert len(results) == 1
    assert results[0].title == "Totally Different Song"
