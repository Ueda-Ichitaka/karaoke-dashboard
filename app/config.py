"""Application configuration, loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Branding
    app_title: str = "Karaoke Dashboard"

    # Database — SQLAlchemy URL. Default matches the bundled docker-compose "db" service.
    database_url: str = "postgresql+psycopg://karaoke:karaoke@db:5432/karaoke"

    # Session signing key. MUST be set to a long random value in production.
    secret_key: str = Field(default="dev-insecure-change-me", min_length=1)

    # Send session cookie only over HTTPS. Set to false for plain-http local testing.
    session_cookie_secure: bool = True

    # Where the karaoke song folders live (mounted into the container).
    songs_dir: str = "/songs"
    # Separator between artist and title in a folder name, e.g. "Queen - Bohemian Rhapsody".
    song_separator: str = " - "
    # Seconds to cache the directory listing before re-scanning from disk.
    scan_cache_seconds: int = 30
    # Folder names (exact) that are never treated as songs.
    song_ignore_names: tuple[str, ...] = ("@eaDir", "#recycle", "#snapshot", "lost+found")

    # Pagination
    page_size: int = 60

    # First-run admin seed. If admin_password is empty, seeding is skipped.
    admin_username: str = "admin"
    admin_password: str = ""

    # Include a header row in the requested-songs CSV export.
    csv_include_header: bool = True

    @property
    def is_dev_secret(self) -> bool:
        return self.secret_key == "dev-insecure-change-me"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
