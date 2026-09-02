import pytest
from pydantic import ValidationError

from app.db.base import build_engine_options, database_pool_summary
from config import DatabaseSettings


def _settings(url: str, **overrides) -> DatabaseSettings:
    values = {"SQLALCHEMY_DATABASE_URL": url, **overrides}
    return DatabaseSettings(_env_file=None, **values)


def test_non_sqlite_pool_defaults_are_bounded_per_process():
    settings = _settings("postgresql+asyncpg://localhost/pasarguard")

    assert settings.pool_size == 5
    assert settings.max_overflow == 5
    assert settings.connection_ceiling() == 10
    assert settings.connection_ceiling(process_count=4) == 40


def test_explicit_pool_overrides_keep_per_process_meaning():
    settings = _settings(
        "postgresql+asyncpg://localhost/pasarguard",
        SQLALCHEMY_POOL_SIZE=12,
        SQLALCHEMY_MAX_OVERFLOW=8,
        SQLALCHEMY_POOL_TIMEOUT=7,
    )

    options = build_engine_options(settings)

    assert settings.connection_ceiling(process_count=3) == 60
    assert options["pool_size"] == 12
    assert options["max_overflow"] == 8
    assert options["pool_timeout"] == 7


def test_sqlite_does_not_receive_queue_pool_options():
    settings = _settings("sqlite+aiosqlite:///db.sqlite3")

    options = build_engine_options(settings)

    assert options["connect_args"] == {"check_same_thread": False}
    assert settings.connection_ceiling(process_count=4) == 0
    assert "pool_size" not in options
    assert "max_overflow" not in options
    assert "pool_timeout" not in options


def test_mysql_keeps_connect_timeout_and_bounded_pool_options():
    settings = _settings(
        "mysql+asyncmy://localhost/pasarguard",
        SQLALCHEMY_CONNECT_TIMEOUT=9,
    )

    options = build_engine_options(settings)

    assert options["connect_args"] == {"connect_timeout": 9}
    assert options["pool_size"] == 5
    assert options["max_overflow"] == 5
    assert options["pool_pre_ping"] is True


def test_pool_summary_reports_process_and_service_ceilings_without_url():
    settings = _settings("postgresql+asyncpg://user:secret@db.example/pasarguard")

    summary = database_pool_summary(settings, process_count=4)

    assert "ceiling=10 connections/process" in summary
    assert "40 across 4 configured process(es)" in summary
    assert "secret" not in summary
    assert "db.example" not in summary


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("SQLALCHEMY_POOL_SIZE", 0),
        ("SQLALCHEMY_MAX_OVERFLOW", -1),
        ("SQLALCHEMY_POOL_RECYCLE", -2),
        ("SQLALCHEMY_POOL_TIMEOUT", 0),
    ],
)
def test_invalid_pool_settings_fail_validation(field: str, value: int):
    with pytest.raises(ValidationError):
        _settings("postgresql+asyncpg://localhost/pasarguard", **{field: value})


def test_connection_ceiling_rejects_invalid_process_count():
    settings = _settings("postgresql+asyncpg://localhost/pasarguard")

    with pytest.raises(ValueError, match="process_count must be at least 1"):
        settings.connection_ceiling(process_count=0)
