"""Unit tests for app/request_matching.py: find_existing_request() must
treat a row still sitting in the pending-review queue (PendingSongRequest)
the same as an already-admitted open SongRequest - either one blocks a
duplicate (same band/song/duet-bucket), per app/duet.py's wants_duet().
"""

from __future__ import annotations

from app.database import SessionLocal
from app.models import PendingSongRequest, SongRequest
from app.request_matching import find_existing_request


def test_matches_a_still_pending_request(fresh_db):
    with SessionLocal() as db:
        db.add(PendingSongRequest(band_name="Journey", song_name="Faithfully", requester_username="admin"))
        db.commit()

        found = find_existing_request(db, "Journey", "Faithfully")
        assert found is not None
        assert isinstance(found, PendingSongRequest)


def test_matches_an_admitted_open_request(fresh_db):
    with SessionLocal() as db:
        db.add(
            SongRequest(
                band_name="Journey", song_name="Faithfully", status="open", requester_username="admin"
            )
        )
        db.commit()

        found = find_existing_request(db, "Journey", "Faithfully")
        assert found is not None
        assert isinstance(found, SongRequest)


def test_pending_duet_bucket_also_applies(fresh_db):
    with SessionLocal() as db:
        db.add(
            PendingSongRequest(
                band_name="Journey", song_name="Faithfully", duet="no", requester_username="admin"
            )
        )
        db.commit()

        assert find_existing_request(db, "Journey", "Faithfully", duet="yes") is None
        assert find_existing_request(db, "Journey", "Faithfully", duet="no") is not None
        assert find_existing_request(db, "Journey", "Faithfully", duet="") is not None
