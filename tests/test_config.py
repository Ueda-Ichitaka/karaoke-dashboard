"""Unit tests for settings / DB URL construction."""

from __future__ import annotations

from app.config import Settings


def test_url_from_parts_encodes_special_chars():
    s = Settings(
        postgres_host="karaoke-db",
        postgres_port=5432,
        postgres_db="karaoke",
        postgres_user="karaoke",
        postgres_password="p@ss/w0rd:#%",
        database_url="",
        secret_key="x",
    )
    url = s.sqlalchemy_url
    # host/port/db must survive intact despite nasty password characters
    assert url.startswith("postgresql+psycopg://karaoke:")
    assert url.endswith("@karaoke-db:5432/karaoke")
    assert "p%40ss%2Fw0rd" in url

    from sqlalchemy.engine import make_url

    parsed = make_url(url)
    assert parsed.host == "karaoke-db"
    assert parsed.port == 5432
    assert parsed.database == "karaoke"
    assert parsed.password == "p@ss/w0rd:#%"


def test_explicit_database_url_wins():
    s = Settings(database_url="sqlite:///./x.db", postgres_password="ignored", secret_key="x")
    assert s.sqlalchemy_url == "sqlite:///./x.db"
    assert "x.db" in s.db_target


def test_db_target_hides_credentials():
    s = Settings(postgres_password="supersecret", postgres_host="h", database_url="", secret_key="x")
    assert "supersecret" not in s.db_target
    assert s.db_target == "h:5432/karaoke"
