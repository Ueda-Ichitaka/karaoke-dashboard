"""About me: one-time startup migration for the pending-review workflow
(app/models.py: PendingSongRequest, PendingBrokenReport). Before this
workflow existed, a submission went straight into SongRequest/BrokenReport
as status="open"; now it must be reviewed and admitted first. Any row that
was already "open" when this shipped is moved into the matching pending
table so it goes through that same review, exactly like a fresh submission.
A "done"/"resolved" row is left alone - it's already finished. Run from
app/database.py's init_db(); naturally idempotent, since a row that was
already moved out is no longer status="open" to match again.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import BrokenReport, PendingBrokenReport, PendingSongRequest, SongRequest


def migrate_open_rows_to_pending(db: Session) -> None:
    open_requests = db.scalars(select(SongRequest).where(SongRequest.status == "open")).all()
    for row in open_requests:
        db.add(
            PendingSongRequest(
                band_name=row.band_name,
                song_name=row.song_name,
                youtube_url=row.youtube_url,
                language=row.language,
                musicbrainz_id=row.musicbrainz_id,
                lyrics_url=row.lyrics_url,
                cover_url=row.cover_url,
                duet=row.duet,
                requester_id=row.requester_id,
                requester_username=row.requester_username,
                created_at=row.created_at,
            )
        )
        db.delete(row)

    open_reports = db.scalars(select(BrokenReport).where(BrokenReport.status == "open")).all()
    for row in open_reports:
        db.add(
            PendingBrokenReport(
                song_folder=row.song_folder,
                category=row.category,
                description=row.description,
                genius_url=row.genius_url,
                language=row.language,
                cover_url=row.cover_url,
                reporter_id=row.reporter_id,
                reporter_username=row.reporter_username,
                created_at=row.created_at,
            )
        )
        db.delete(row)
