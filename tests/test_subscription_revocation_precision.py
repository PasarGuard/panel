from datetime import UTC, datetime
from importlib import import_module

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import mysql
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models import User

migration = import_module("app.db.migrations.versions.9e0d7a1c4b52_preserve_subscription_revocation_microseconds")


@pytest.mark.parametrize("column_name", ["created_at", "sub_revoked_at"])
def test_mysql_subscription_token_columns_use_microsecond_precision(column_name):
    column_type = User.__table__.c[column_name].type.dialect_impl(mysql.dialect())

    assert column_type.fsp == 6


def test_mysql_migration_upgrades_both_subscription_token_timestamps(monkeypatch):
    altered_columns: list[tuple[str, str, int | None]] = []

    def capture_alter_column(table_name, column_name, **kwargs):
        altered_columns.append((table_name, column_name, kwargs["type_"].fsp))

    monkeypatch.setattr(migration, "_is_mysql_family", lambda: True)
    monkeypatch.setattr(migration.op, "alter_column", capture_alter_column)

    migration.upgrade()

    assert altered_columns == [
        ("users", "created_at", 6),
        ("users", "sub_revoked_at", 6),
    ]


def test_migration_is_stacked_after_namespace_rollout():
    assert migration.down_revision == "d12f6a8b9c30"
    assert "Deployment order is strict" in migration.__doc__


def test_mysql_downgrade_rounds_revocations_up_before_precision_loss(monkeypatch):
    statements: list[str] = []
    altered_columns: list[str] = []
    monkeypatch.setattr(migration, "_is_mysql_family", lambda: True)
    monkeypatch.setattr(migration.op, "execute", lambda statement: statements.append(str(statement)))
    monkeypatch.setattr(
        migration.op,
        "alter_column",
        lambda _table_name, column_name, **_kwargs: altered_columns.append(column_name),
    )

    migration.downgrade()

    assert "DATE_ADD" in statements[0]
    assert "MICROSECOND(sub_revoked_at)" in statements[0]
    assert altered_columns == ["sub_revoked_at", "created_at"]


@pytest.mark.asyncio
async def test_subscription_revocation_microseconds_survive_database_round_trip():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    timestamp = datetime(2026, 8, 9, 12, 0, 0, 123456, tzinfo=UTC)

    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: User.__table__.create(sync, checkfirst=True))

    async with session_factory() as session:
        await session.execute(
            User.__table__.insert().values(
                sync_id="revocation-precision-sync",
                username="revocation-precision",
                status="active",
                proxy_settings={},
                used_traffic=0,
                created_at=timestamp,
                sub_revoked_at=timestamp,
            )
        )
        await session.commit()
        stored = (await session.execute(select(User.sub_revoked_at))).scalar_one()

    assert stored.microsecond == 123456
    await engine.dispose()
