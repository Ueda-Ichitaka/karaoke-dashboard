"""Tests for app/duplicates.py: duplicate-song detection and field diffing."""

from __future__ import annotations

from app import duplicates, songs


def test_normalize_key_folds_case_and_whitespace():
    assert duplicates.normalize_key("  Copycat   Song ") == "copycat song"
    assert duplicates.normalize_key("COPYCAT SONG") == "copycat song"
    assert duplicates.normalize_key(None) == ""


def test_find_duplicate_groups_finds_the_two_solo_copies(fresh_db):
    from app.database import SessionLocal

    with SessionLocal() as db:
        groups = duplicates.find_duplicate_groups(db)

    matches = [g for g in groups if g.title_key == "copycat song"]
    assert len(matches) == 1
    group = matches[0]
    assert group.is_duet is False
    assert len(group.entries) == 2
    folders = {e.folder for e in group.entries}
    assert folders == {"Coverband - Copycat Song", "Coverband - Copycat Song (Reupload)"}


def test_duet_variant_is_not_grouped_with_solo_copies(fresh_db):
    from app.database import SessionLocal

    with SessionLocal() as db:
        groups = duplicates.find_duplicate_groups(db)

    duet_groups = [g for g in groups if g.title_key == "copycat song" and g.is_duet]
    assert duet_groups == []  # only one duet copy exists - nothing to duplicate it


def test_unique_songs_are_not_reported_as_duplicates(fresh_db):
    from app.database import SessionLocal

    with SessionLocal() as db:
        groups = duplicates.find_duplicate_groups(db)

    assert all(g.title_key != "solo song" for g in groups)
    assert all(g.title_key not in ("song a", "song b") for g in groups)


def test_field_diff_flags_differing_fields_only(fresh_db):
    from app.database import SessionLocal

    with SessionLocal() as db:
        group = next(g for g in duplicates.find_duplicate_groups(db) if g.title_key == "copycat song")

    rows = {row.label: row for row in duplicates.field_diff(group)}
    assert rows["Genre"].differs is True
    assert rows["Genre"].values == ["Rock", "Pop"]
    assert rows["Artist"].differs is False


def test_dismiss_removes_group_from_future_lookups(fresh_db):
    from app.database import SessionLocal

    with SessionLocal() as db:
        group = next(g for g in duplicates.find_duplicate_groups(db) if g.title_key == "copycat song")
        duplicates.dismiss_group(db, group, dismissed_by="admin")

    with SessionLocal() as db:
        groups_after = duplicates.find_duplicate_groups(db)
        assert all(g.title_key != "copycat song" for g in groups_after)

        # get_duplicate_group still finds it directly (e.g. to view/undo later)
        still_found = duplicates.get_duplicate_group(db, group.group_id)
        assert still_found is not None
        assert duplicates.is_dismissed(db, still_found) is True


def test_dismiss_is_idempotent(fresh_db):
    from app.database import SessionLocal

    with SessionLocal() as db:
        group = next(g for g in duplicates.find_duplicate_groups(db) if g.title_key == "copycat song")
        duplicates.dismiss_group(db, group, dismissed_by="admin")
        duplicates.dismiss_group(db, group, dismissed_by="admin")  # must not raise/duplicate-insert


# ----------------------------------------------------------------------- cache
# Scanning every folder's UltraStar tags is expensive, so results are cached
# in memory (see app/duplicates.py) until explicitly refreshed - by an admin's
# "Rescan" button or the scheduled monthly job (see app/scheduler.py).
def test_find_duplicate_groups_does_not_rescan_when_cache_is_warm(fresh_db, monkeypatch):
    from app.database import SessionLocal

    duplicates.refresh_cache()  # prime a known-fresh cache

    calls = []
    monkeypatch.setattr(songs, "all_songs", lambda: calls.append(1) or [])

    with SessionLocal() as db:
        duplicates.find_duplicate_groups(db)
        duplicates.find_duplicate_groups(db)
    assert calls == []


def test_refresh_cache_forces_a_rescan(fresh_db, monkeypatch):
    calls = []
    real_all_songs = songs.all_songs
    monkeypatch.setattr(songs, "all_songs", lambda: (calls.append(1), real_all_songs())[1])

    duplicates.refresh_cache()
    assert len(calls) == 1


def test_last_scanned_at_updates_after_refresh(fresh_db):
    duplicates.refresh_cache()
    first = duplicates.last_scanned_at()
    assert first is not None
    duplicates.refresh_cache()
    second = duplicates.last_scanned_at()
    assert second >= first
