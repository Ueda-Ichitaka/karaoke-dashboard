"""Unit tests for the UltraStar .txt metadata parser (app/ultrastar.py).

Written before the implementation (TDD): every test below fails on an
un-implemented app.ultrastar until the parser exists.
"""

from __future__ import annotations

import wave
from pathlib import Path

from app import ultrastar
from tests.conftest import SONGS_DIR


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def _write_silent_wav(path: Path, seconds: float, framerate: int = 100) -> None:
    """A minimal, valid audio file of an exact known duration, for length tests."""
    n_frames = round(seconds * framerate)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(framerate)
        w.writeframes(b"\x00" * n_frames)


def test_parses_core_tags(tmp_path):
    path = _write(
        tmp_path,
        "song.txt",
        "#TITLE:Bohemian Rhapsody\n"
        "#ARTIST:Queen\n"
        "#GENRE:Rock\n"
        "#YEAR:1975\n"
        "#LANGUAGE:English\n"
        "#BPM:200\n"
        "#GAP:1000\n"
        ": 0 4 0 La\n",
    )
    meta = ultrastar.parse_song_file(path)
    assert meta is not None
    assert meta.title == "Bohemian Rhapsody"
    assert meta.artist == "Queen"
    assert meta.genre == "Rock"
    assert meta.year == 1975
    assert meta.language == "English"
    assert meta.source_file == "song.txt"
    assert meta.is_duet is False


def test_missing_bpm_and_gap_is_not_a_song_file(tmp_path):
    path = _write(tmp_path, "readme.txt", "just some notes\n")
    assert ultrastar.parse_song_file(path) is None


def test_missing_optional_tags_are_none(tmp_path):
    path = _write(tmp_path, "song.txt", "#TITLE:X\n#ARTIST:Y\n#BPM:100\n#GAP:0\n")
    meta = ultrastar.parse_song_file(path)
    assert meta.genre is None
    assert meta.year is None
    assert meta.language is None
    assert meta.length_seconds is None
    assert meta.cover_file is None


def test_title_and_artist_fall_back_when_absent(tmp_path):
    path = _write(tmp_path, "mystery.txt", "#BPM:100\n#GAP:0\n")
    meta = ultrastar.parse_song_file(path)
    assert meta is not None
    assert meta.title == "mystery"
    assert meta.artist is None


def test_duet_detected_from_duetsinger_tags(tmp_path):
    path = _write(
        tmp_path,
        "duet.txt",
        "#TITLE:Two Voices\n#ARTIST:Duo\n#DUETSINGERP1:Alice\n#DUETSINGERP2:Bob\n#BPM:100\n#GAP:0\n",
    )
    meta = ultrastar.parse_song_file(path)
    assert meta.is_duet is True
    assert meta.duet_singers == ("Alice", "Bob")


def test_non_duet_has_no_singers(tmp_path):
    path = _write(tmp_path, "solo.txt", "#TITLE:X\n#ARTIST:Y\n#BPM:100\n#GAP:0\n")
    meta = ultrastar.parse_song_file(path)
    assert meta.is_duet is False
    assert meta.duet_singers is None


def test_cover_resolved_only_if_file_exists(tmp_path):
    (tmp_path / "cover.jpg").write_bytes(b"fake")
    path = _write(tmp_path, "song.txt", "#TITLE:X\n#ARTIST:Y\n#COVER:cover.jpg\n#BPM:100\n#GAP:0\n")
    meta = ultrastar.parse_song_file(path)
    assert meta.cover_file == "cover.jpg"

    path2 = _write(tmp_path, "song2.txt", "#TITLE:X\n#ARTIST:Y\n#COVER:missing.jpg\n#BPM:100\n#GAP:0\n")
    meta2 = ultrastar.parse_song_file(path2)
    assert meta2.cover_file is None


def test_length_from_referenced_audio_file(tmp_path):
    # The karaoke system plays the #MP3 file back, so its real duration is
    # the song's length - more reliable than the rarely-present UltraStar
    # #START/#END tags.
    _write_silent_wav(tmp_path / "song.wav", seconds=125)
    path = _write(tmp_path, "song.txt", "#TITLE:X\n#ARTIST:Y\n#BPM:100\n#GAP:0\n#MP3:song.wav\n")
    meta = ultrastar.parse_song_file(path)
    assert meta.length_seconds is not None
    assert round(meta.length_seconds) == 125
    assert meta.length_display == "2:05"


def test_length_prefers_audio_tag_over_mp3_tag(tmp_path):
    _write_silent_wav(tmp_path / "real.wav", seconds=10)
    _write_silent_wav(tmp_path / "other.wav", seconds=99)
    path = _write(
        tmp_path, "song.txt", "#TITLE:X\n#ARTIST:Y\n#BPM:100\n#GAP:0\n#AUDIO:real.wav\n#MP3:other.wav\n"
    )
    meta = ultrastar.parse_song_file(path)
    assert round(meta.length_seconds) == 10


def test_length_falls_back_to_video_file(tmp_path):
    _write_silent_wav(tmp_path / "clip.wav", seconds=42)
    path = _write(tmp_path, "song.txt", "#TITLE:X\n#ARTIST:Y\n#BPM:100\n#GAP:0\n#VIDEO:clip.wav\n")
    meta = ultrastar.parse_song_file(path)
    assert round(meta.length_seconds) == 42


def test_length_none_when_media_file_missing(tmp_path):
    path = _write(tmp_path, "song.txt", "#TITLE:X\n#ARTIST:Y\n#BPM:100\n#GAP:0\n#MP3:missing.mp3\n")
    meta = ultrastar.parse_song_file(path)
    assert meta.length_seconds is None


def test_length_none_when_no_media_tag_present(tmp_path):
    path = _write(tmp_path, "song.txt", "#TITLE:X\n#ARTIST:Y\n#BPM:100\n#GAP:0\n")
    meta = ultrastar.parse_song_file(path)
    assert meta.length_seconds is None


def test_length_none_for_unreadable_media_file(tmp_path):
    (tmp_path / "broken.mp3").write_bytes(b"not really audio data")
    path = _write(tmp_path, "song.txt", "#TITLE:X\n#ARTIST:Y\n#BPM:100\n#GAP:0\n#MP3:broken.mp3\n")
    meta = ultrastar.parse_song_file(path)
    assert meta.length_seconds is None


def test_scan_folder_songs_finds_all_txt_files():
    assert SONGS_DIR.exists()  # sanity: fixture dir is the one being scanned
    metas = ultrastar.scan_folder_songs("Testband - Multi Song")
    titles = sorted(m.title for m in metas)
    assert titles == ["Song A", "Song B"]


def test_scan_folder_songs_skips_non_ultrastar_txt():
    metas = ultrastar.scan_folder_songs("Testband - Junk Text")
    assert metas == []


def test_scan_folder_songs_empty_for_missing_folder():
    assert ultrastar.scan_folder_songs("Does Not Exist") == []


def test_scan_folder_songs_single_solo_song():
    metas = ultrastar.scan_folder_songs("Testband - Solo Song")
    assert len(metas) == 1
    meta = metas[0]
    assert meta.title == "Solo Song"
    assert meta.cover_file == "cover.jpg"
    assert meta.length_display == "3:00"
