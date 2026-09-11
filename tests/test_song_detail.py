"""Route-level tests for the song-detail feature (metadata + cover serving).

Written before the implementation (TDD): these fail against the current
/songs routes until the detail rendering and cover route exist.
"""

from __future__ import annotations


def test_song_list_shows_metadata_for_solo_song(client):
    r = client.get("/songs")
    assert r.status_code == 200
    assert "Solo Song" in r.text
    assert "Rock" in r.text
    assert "1999" in r.text
    assert "English" in r.text
    assert "3:00" in r.text


def test_song_list_distinguishes_multiple_versions_in_one_folder(client):
    r = client.get("/songs")
    assert "Song A" in r.text
    assert "Song B" in r.text
    assert "SongA.txt" in r.text
    assert "SongB.txt" in r.text


def test_song_list_shows_duet_badge_and_singers(client):
    r = client.get("/songs")
    assert "Duet Song" in r.text
    assert "Alice" in r.text
    assert "Bob" in r.text


def test_song_list_folder_without_txt_does_not_crash(client):
    # "Queen - Bohemian Rhapsody" has no UltraStar .txt file in the fixtures.
    r = client.get("/songs")
    assert r.status_code == 200
    assert "Bohemian Rhapsody" in r.text


def test_cover_route_serves_existing_image(client):
    r = client.get("/songs/Testband - Solo Song/cover/cover.jpg")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert r.content.startswith(b"\xff\xd8\xff")


def test_cover_route_unknown_folder_is_404(client):
    r = client.get("/songs/Does Not Exist/cover/cover.jpg")
    assert r.status_code == 404


def test_cover_route_unknown_file_is_404(client):
    r = client.get("/songs/Testband - Solo Song/cover/missing.jpg")
    assert r.status_code == 404


def test_cover_route_rejects_path_traversal(client):
    r = client.get("/songs/Testband - Solo Song/cover/..%2f..%2fsongs.py")
    assert r.status_code == 404


def test_cover_route_rejects_non_image_extension(client):
    # The song's own .txt file exists on disk but must not be servable as a "cover".
    r = client.get("/songs/Testband - Solo Song/cover/Solo Song.txt")
    assert r.status_code == 404
