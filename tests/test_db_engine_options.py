import pytest

from app.db.base import build_engine_options
from config import DatabaseSettings


def test_build_engine_options_postgresql_asyncpg_sets_timeout():
    settings = DatabaseSettings(
        SQLALCHEMY_DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/pasarguard",
        SQLALCHEMY_CONNECT_TIMEOUT=12,
        SQLALCHEMY_POOL_SIZE=7,
        SQLALCHEMY_MAX_OVERFLOW=9,
        SQLALCHEMY_POOL_RECYCLE=180,
        SQLALCHEMY_POOL_TIMEOUT=8,
        ECHO_SQL_QUERIES=True,
    )

    options = build_engine_options(settings)

    assert options == {
        "connect_args": {"timeout": 12},
        "echo": True,
        "pool_size": 7,
        "max_overflow": 9,
        "pool_recycle": 180,
        "pool_timeout": 8,
        "pool_pre_ping": True,
    }


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://user:pass@localhost:5432/pasarguard",
        "postgresql+psycopg://user:pass@localhost:5432/asyncpg_db",
    ],
)
def test_build_engine_options_postgresql_non_asyncpg_omits_asyncpg_timeout(url: str):
    settings = DatabaseSettings(
        SQLALCHEMY_DATABASE_URL=url,
        SQLALCHEMY_CONNECT_TIMEOUT=12,
    )

    options = build_engine_options(settings)

    assert options["connect_args"] == {}
    assert options["pool_pre_ping"] is True


def test_build_engine_options_mysql_sets_connect_timeout():
    settings = DatabaseSettings(
        SQLALCHEMY_DATABASE_URL="mysql+asyncmy://user:pass@localhost:3306/pasarguard",
        SQLALCHEMY_CONNECT_TIMEOUT=9,
        SQLALCHEMY_POOL_SIZE=4,
        SQLALCHEMY_MAX_OVERFLOW=6,
        SQLALCHEMY_POOL_RECYCLE=240,
        SQLALCHEMY_POOL_TIMEOUT=11,
        ECHO_SQL_QUERIES=False,
    )

    options = build_engine_options(settings)

    assert options == {
        "connect_args": {"connect_timeout": 9},
        "echo": False,
        "pool_size": 4,
        "max_overflow": 6,
        "pool_recycle": 240,
        "pool_timeout": 11,
        "pool_pre_ping": True,
    }


def test_build_engine_options_sqlite_sets_check_same_thread_without_pool_kwargs():
    settings = DatabaseSettings(
        SQLALCHEMY_DATABASE_URL="sqlite+aiosqlite:///db.sqlite3",
        SQLALCHEMY_CONNECT_TIMEOUT=9,
        ECHO_SQL_QUERIES=False,
    )

    options = build_engine_options(settings)

    assert options == {
        "connect_args": {"check_same_thread": False},
        "echo": False,
    }
