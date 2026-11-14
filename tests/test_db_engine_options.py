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


def test_build_engine_options_postgresql_asyncpg_keeps_timeout_from_url():
    settings = DatabaseSettings(
        SQLALCHEMY_DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/pasarguard?timeout=30",
        SQLALCHEMY_CONNECT_TIMEOUT=12,
    )

    assert build_engine_options(settings)["connect_args"] == {"timeout": 30.0}
