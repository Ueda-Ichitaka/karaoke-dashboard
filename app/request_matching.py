"""About me: checks whether a song request matches something already in the
library, for the admin requests view's "scan" indicator. Two kinds of match:
an exact "<band> - <song>" folder name (see songs.folder_exists), or just a
matching UltraStar artist/title tag pair inside a folder that doesn't follow
that naming convention (e.g. one produced by another library-management
tool) - the same normalized-key comparison app/duplicates.py uses for
cross-folder duplicate detection.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import duplicates, songs, ultrastar


@dataclass(frozen=True, slots=True)
class LibraryMatch:
    folder: str
    exact_folder: bool  # True: folder name itself matched. False: only the tags did.


def find_library_match(band_name: str, song_name: str) -> LibraryMatch | None:
    band_name = band_name.strip()
    song_name = song_name.strip()
    if not band_name or not song_name:
        return None

    folder = songs.folder_exists(band_name, song_name)
    if folder:
        return LibraryMatch(folder=folder, exact_folder=True)

    target_artist = duplicates.normalize_key(band_name)
    target_title = duplicates.normalize_key(song_name)
    for song in songs.all_songs():
        for meta in ultrastar.scan_folder_songs(song.folder):
            artist_matches = duplicates.normalize_key(meta.artist) == target_artist
            title_matches = duplicates.normalize_key(meta.title) == target_title
            if artist_matches and title_matches:
                return LibraryMatch(folder=song.folder, exact_folder=False)
    return None
