"""SQLAlchemy ORM models."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _now() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    broken_reports: Mapped[list[BrokenReport]] = relationship(back_populates="reporter")
    song_requests: Mapped[list[SongRequest]] = relationship(back_populates="requester")


class BrokenReport(Base):
    __tablename__ = "broken_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Raw folder name as it exists on disk, plus best-effort parsed parts.
    song_folder: Mapped[str] = mapped_column(String(512), index=True)
    song_artist: Mapped[str | None] = mapped_column(String(512), nullable=True)
    song_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)  # open | resolved

    reporter_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reporter_username: Mapped[str] = mapped_column(String(64))  # snapshot, survives user deletion
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    reporter: Mapped[User | None] = relationship(back_populates="broken_reports")


class SongRequest(Base):
    __tablename__ = "song_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    band_name: Mapped[str] = mapped_column(String(512))
    song_name: Mapped[str] = mapped_column(String(512))
    youtube_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)  # open | done

    requester_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    requester_username: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    requester: Mapped[User | None] = relationship(back_populates="song_requests")


class DismissedDuplicate(Base):
    """An admin-reviewed duplicate-song group that should stop being reported.

    Duplicate groups are computed live from the filesystem (see
    app/duplicates.py), not stored - a row here just remembers the group's
    normalized (artist, title, duet) key so a future rescan skips it.
    """

    __tablename__ = "dismissed_duplicates"
    __table_args__ = (UniqueConstraint("artist_key", "title_key", "is_duet", name="uq_dismissed_duplicate_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    artist_key: Mapped[str] = mapped_column(String(512))
    title_key: Mapped[str] = mapped_column(String(512))
    is_duet: Mapped[bool] = mapped_column(Boolean)
    dismissed_by_username: Mapped[str] = mapped_column(String(64))
    dismissed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
