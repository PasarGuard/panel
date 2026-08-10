from alembic.command import upgrade
from alembic.config import Config
from sqlalchemy import create_engine, text

PARENT_REVISION = "fb32155473c1"
RESET_SOURCE_REVISION = "b8e4e47b9f2c"


def _upgrade(database_url: str, revision: str) -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    upgrade(config, revision)


def test_legacy_usage_logs_are_not_backfilled_as_scheduled(tmp_path):
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'legacy-reset-source.db'}"
    _upgrade(database_url, PARENT_REVISION)

    engine = create_engine(database_url.replace("sqlite+aiosqlite", "sqlite"))
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO user_usage_logs "
                "(user_id, used_traffic_at_reset, reset_at) "
                "VALUES (NULL, 1024, CURRENT_TIMESTAMP)"
            )
        )

    _upgrade(database_url, RESET_SOURCE_REVISION)

    with engine.begin() as connection:
        # This is how an old process writes during a rolling upgrade: it knows
        # nothing about reset_source and relies on the database default.
        connection.execute(
            text(
                "INSERT INTO user_usage_logs "
                "(user_id, used_traffic_at_reset, reset_at) "
                "VALUES (NULL, 2048, CURRENT_TIMESTAMP)"
            )
        )
        reset_sources = connection.execute(
            text("SELECT reset_source FROM user_usage_logs ORDER BY id")
        ).scalars().all()

    assert reset_sources == ["legacy", "legacy"]
