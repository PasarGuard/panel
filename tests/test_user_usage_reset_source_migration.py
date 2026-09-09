from alembic.command import downgrade, upgrade
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

PARENT_REVISION = "8e2f1a9c4b70"
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
        reset_sources = connection.execute(text("SELECT reset_source FROM user_usage_logs ORDER BY id")).scalars().all()

    assert reset_sources == ["legacy", "legacy"]


def test_standalone_head_and_downgrade_preserve_usage_history(tmp_path):
    config = Config("alembic.ini")
    assert ScriptDirectory.from_config(config).get_heads() == [RESET_SOURCE_REVISION]
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'reset-source-roundtrip.db'}"
    config.set_main_option("sqlalchemy.url", database_url)
    upgrade(config, "head")
    engine = create_engine(database_url.replace("sqlite+aiosqlite", "sqlite"))
    with engine.begin() as connection:
        for source in ("legacy", "manual", "scheduled", "next_plan"):
            connection.execute(
                text(
                    "INSERT INTO user_usage_logs (user_id, used_traffic_at_reset, reset_at, reset_source) "
                    "VALUES (NULL, 123, '2026-01-02 03:04:05', :source)"
                ),
                {"source": source},
            )
        before = connection.execute(
            text("SELECT id, used_traffic_at_reset, reset_at FROM user_usage_logs ORDER BY id")
        ).all()
        assert "ix_user_usage_logs_user_id_source_reset_at" in {
            i["name"] for i in inspect(connection).get_indexes("user_usage_logs")
        }
    upgrade(config, "head")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT reset_source FROM user_usage_logs ORDER BY id")).scalars().all() == [
            "legacy",
            "manual",
            "scheduled",
            "next_plan",
        ]
    downgrade(config, PARENT_REVISION)
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT id, used_traffic_at_reset, reset_at FROM user_usage_logs ORDER BY id")
            ).all()
            == before
        )
        assert "reset_source" not in {c["name"] for c in inspect(connection).get_columns("user_usage_logs")}
    upgrade(config, "head")
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT id, used_traffic_at_reset, reset_at FROM user_usage_logs ORDER BY id")
            ).all()
            == before
        )
        # Downgrade necessarily removes provenance; a re-upgrade must not guess it.
        assert (
            connection.execute(text("SELECT reset_source FROM user_usage_logs ORDER BY id")).scalars().all()
            == ["legacy"] * 4
        )
    engine.dispose()
