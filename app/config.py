"""Application configuration, loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import quote

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Branding
    app_title: str = "Karaoke Dashboard"

    # --- Database -------------------------------------------------------------
    # Preferred: give the connection as discrete parts. The password is URL-encoded
    # by the app, so it may contain @ : / # % and other special characters.
    postgres_host: str = "db"
    postgres_port: int = 5432
    postgres_db: str = "karaoke"
    postgres_user: str = "karaoke"
    postgres_password: str = "karaoke"

    # Optional escape hatch: a full SQLAlchemy URL. When set, it wins over the
    # POSTGRES_* parts above (e.g. "sqlite:///./dev.db" or a managed-DB URL).
    database_url: str = ""

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
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        user = quote(self.postgres_user, safe="")
        password = quote(self.postgres_password, safe="")
        return (
            f"postgresql+psycopg://{user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def db_target(self) -> str:
        """Human-readable host:port/db for logs (no credentials)."""
        if self.database_url:
            return self.database_url.split("@")[-1] or self.database_url
        return f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    @property
    def is_dev_secret(self) -> bool:
        return self.secret_key == "dev-insecure-change-me"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
