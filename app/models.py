"""SQLAlchemy ORM models."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
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
    # Between a plain user and an admin: may use the Reported, Requested and
    # Duplicates pages and edit genres (app/deps.py: require_contributor).
    # Nullable so _sync_schema can auto-add it to an existing users table;
    # NULL counts as False.
    is_contributor: Mapped[bool | None] = mapped_column(Boolean, default=False, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    broken_reports: Mapped[list[BrokenReport]] = relationship(back_populates="reporter")
    song_requests: Mapped[list[SongRequest]] = relationship(back_populates="requester")

    @property
    def can_contribute(self) -> bool:
        """A contributor or an admin."""
        return bool(self.is_admin or self.is_contributor)

    @property
    def role(self) -> str:
        """admin, contributor or user - the highest level the user has."""
        return "admin" if self.is_admin else "contributor" if self.is_contributor else "user"


class BrokenReport(Base):
    __tablename__ = "broken_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Raw folder name as it exists on disk, plus best-effort parsed parts.
    song_folder: Mapped[str] = mapped_column(String(512), index=True)
    song_artist: Mapped[str | None] = mapped_column(String(512), nullable=True)
    song_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # See app/broken_categories.py for the fixed choice list. Nullable here so
    # reports created before this field existed still load - the app itself
    # always requires it on a new submission.
    category: Mapped[str | None] = mapped_column(String(16), nullable=True)
    description: Mapped[str] = mapped_column(Text)
    # A genius.com or lrclib.net lyrics link, required (at the app level) for the "lyrics
    # broken" / "song goes out of sync" categories so the admin has a
    # reference for what the correct lyrics/timing should be.
    genius_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # ISO 639-1 code, or "mixed" (see app/languages.py). Nullable here so
    # reports created before this field existed still load - the app itself
    # always requires it on a new submission.
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    cover_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)  # optional cover image link
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)  # open | resolved
    # Admin-only, set when reviewing the report (app/genres.py, app/traits.py)
    # - never on the public form. Nullable so _sync_schema can auto-add these
    # to the already-existing table; a NULL row predates the fields and is
    # treated the same as its default by every reader (app/routes/admin.py).
    # Comma-joined - see app/genres.py and app/traits.py.
    genre: Mapped[str | None] = mapped_column(String(128), nullable=True, default="default")
    trait: Mapped[str | None] = mapped_column(String(128), nullable=True, default="none")

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

    # Optional fields consumed by the UltraSinger CSV import (see
    # UPSTREAM_REQUESTS.md); all three are best-effort and never validated
    # beyond form-level checks - an unresolvable value is silently ignored
    # downstream, not an error.
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)  # ISO 639-1, e.g. "de"
    musicbrainz_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lyrics_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)  # URL or admin-set filesystem path
    cover_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)  # optional cover image link
    duet: Mapped[str | None] = mapped_column(String(3), nullable=True)  # "yes" | "no" | NULL (not said)
    # Admin-only, set when reviewing the request (app/genres.py, app/traits.py)
    # - never on the public form. Nullable so _sync_schema can auto-add these
    # to the already-existing table; a NULL row predates the fields and is
    # treated the same as its default by every reader (app/routes/admin.py).
    # Comma-joined - see app/genres.py and app/traits.py.
    genre: Mapped[str | None] = mapped_column(String(128), nullable=True, default="default")
    trait: Mapped[str | None] = mapped_column(String(128), nullable=True, default="none")

    requester_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    requester_username: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    requester: Mapped[User | None] = relationship(back_populates="song_requests")


class AppSettings(Base):
    """Admin-editable app-wide settings - the karaoke-night/strict profile
    for each of the two public forms (see app/profiles.py, app/app_settings.py),
    the production/debug mode (see app/app_mode.py), the "Reported broken"
    badge mode (see app/broken_badge.py), the library scan schedule (see
    app/scheduler.py), the "What's new" period (see app/recent_period.py)
    and the number of genres on the Genres page's map (app/genre_layout.py).
    A singleton row, always id=1.
    """

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_profile: Mapped[str] = mapped_column(String(16), default="karaoke_night", nullable=False)
    report_profile: Mapped[str] = mapped_column(String(16), default="strict", nullable=False)
    # "production" | "debug" (app/app_mode.py). Nullable so _sync_schema can
    # auto-add it to an already-existing app_settings table (see
    # app/database.py); a NULL row is normalized to "production" by
    # app/app_settings.py: get_app_settings().
    mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Independent of mode - silences all logging (app/app_logging.py) when
    # False, regardless of level. Nullable for the same ALTER-TABLE reason
    # as mode; a NULL row is normalized to True by get_app_settings().
    logging_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # When the public "Reported broken" badge goes away (app/broken_badge.py).
    # Nullable for the same ALTER-TABLE reason as mode; a NULL row is
    # normalized to "until_resolved" by get_app_settings().
    broken_badge: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # The library scan's schedule, a standard cron expression
    # (app/scheduler.py). Nullable for the same ALTER-TABLE reason as mode;
    # a NULL row is normalized to DEFAULT_LIBRARY_SCAN_CRON by
    # get_app_settings().
    library_scan_cron: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # How far back the "What's new" lists reach: a whole number of a unit
    # (app/recent_period.py). Nullable for the same ALTER-TABLE reason as
    # mode; NULL is normalized to 2 months by get_app_settings().
    recent_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recent_unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # How many of the biggest genres get their own cluster on the Genres
    # page's Map and Connections tabs (app/genre_layout.py). Nullable for the
    # same ALTER-TABLE reason as mode; NULL is normalized to
    # DEFAULT_GENRE_MAP_SIZE by get_app_settings().
    genre_map_size: Mapped[int | None] = mapped_column(Integer, nullable=True)


class PendingSongRequest(Base):
    """A newly submitted song request, awaiting admin review before it can
    be admitted into SongRequest (the exportable list) - see
    app/routes/admin.py's request admit/discard routes. Mirrors SongRequest's
    fields exactly; an admitted row is copied over and this one is deleted.
    """

    __tablename__ = "pending_song_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    band_name: Mapped[str] = mapped_column(String(512))
    song_name: Mapped[str] = mapped_column(String(512))
    youtube_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    musicbrainz_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lyrics_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    cover_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    duet: Mapped[str | None] = mapped_column(String(3), nullable=True)
    genre: Mapped[str | None] = mapped_column(String(128), nullable=True, default="default")
    trait: Mapped[str | None] = mapped_column(String(128), nullable=True, default="none")

    requester_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    requester_username: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class PendingBrokenReport(Base):
    """A newly submitted broken-song report, awaiting admin review before it
    can be admitted into BrokenReport (the exportable list) - see
    app/routes/admin.py's report admit/discard routes. Mirrors BrokenReport's
    fields exactly (minus song_artist/song_title, re-derived on admit); an
    admitted row is copied over and this one is deleted.
    """

    __tablename__ = "pending_broken_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    song_folder: Mapped[str] = mapped_column(String(512), index=True)
    category: Mapped[str | None] = mapped_column(String(16), nullable=True)
    description: Mapped[str] = mapped_column(Text)
    genius_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    cover_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    genre: Mapped[str | None] = mapped_column(String(128), nullable=True, default="default")
    trait: Mapped[str | None] = mapped_column(String(128), nullable=True, default="none")

    reporter_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reporter_username: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


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


class LibraryFolder(Base):
    """What the library scan (app/library_history.py) knows about one song
    folder: when it first appeared, whether it follows the flat
    "Artist - Title" convention, its song files' write times and sizes, and
    when one of them was last written - behind the "Recently added" and
    "Recently updated" lists on /songs. A row outlives its folder, so a
    folder that comes back keeps its dates. Every column but the folder is
    nullable so _sync_schema can add it to an existing table.
    """

    __tablename__ = "library_folders"

    id: Mapped[int] = mapped_column(primary_key=True)
    folder: Mapped[str] = mapped_column(String(512), unique=True)
    # NULL: already in the library at the very first scan, so never
    # "recently added".
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    follows_convention: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # JSON {filename: [mtime, size]} of the .txt/.mp3/.opus files directly
    # in the folder, as of the last scan.
    files: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Write time of the newest change to one of those files (NULL: none
    # since the folder was recorded) - behind "Recently updated".
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    # Newest write time of those files any scan has read, the very first
    # included (NULL: none seen) - what a report's time is compared with.
    last_write_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SongGenre(Base):
    """One genre of one song folder, as the library scan
    (app/library_history.py, app/song_genres.py) read it from the #GENRE tag
    of the folder's song files - behind the Genres page. A folder without a
    genre has no row; position keeps the order the files name them in.
    """

    __tablename__ = "song_genres"
    __table_args__ = (UniqueConstraint("folder", "genre", name="uq_song_genre"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    folder: Mapped[str] = mapped_column(String(512), index=True)
    genre: Mapped[str] = mapped_column(String(128), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class GenreEdit(Base):
    """A song folder's genres as a contributor set them on the Genres page's
    Edit tab (app/song_genres.py), until the song files say the same: the
    Genres page shows these instead of the folder's SongGenre rows, the
    Edit tab's export hands them to the USDX Song Factory, and the library
    scan drops the edit once it reads the same genres from the files.
    genres is the comma-joined list ("Symphonic, Metal").
    """

    __tablename__ = "genre_edits"

    id: Mapped[int] = mapped_column(primary_key=True)
    folder: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    genres: Mapped[str] = mapped_column(Text)
    edited_by: Mapped[str] = mapped_column(String(64))
    edited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
