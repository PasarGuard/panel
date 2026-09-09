import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.dialects import mysql, postgresql


def _load_migration_module():
    path = Path("app/db/migrations/versions/d12f6a8b9c30_add_bridge_sync_namespaces.py")
    spec = importlib.util.spec_from_file_location("bridge_sync_namespace_migration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_namespace_migration_backfills_existing_node_and_user(monkeypatch):
    module = _load_migration_module()
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    nodes = sa.Table("nodes", metadata, sa.Column("id", sa.Integer, primary_key=True))
    users = sa.Table("users", metadata, sa.Column("id", sa.Integer, primary_key=True))
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(nodes.insert(), [{"id": 1}])
        connection.execute(users.insert(), [{"id": 7}])
        monkeypatch.setattr(module, "op", Operations(MigrationContext.configure(connection)))

        module.upgrade()

        bridge_id = connection.execute(sa.text("SELECT bridge_id FROM nodes WHERE id = 1")).scalar_one()
        sync_id = connection.execute(sa.text("SELECT sync_id FROM users WHERE id = 7")).scalar_one()
        node_constraints = sa.inspect(connection).get_unique_constraints("nodes")
        user_constraints = sa.inspect(connection).get_unique_constraints("users")

    assert bridge_id == "1"
    assert sync_id == "7"
    assert {item["name"] for item in node_constraints} == {"uq_nodes_bridge_id"}
    assert {item["name"] for item in user_constraints} == {"uq_users_sync_id"}


def test_namespace_backfill_uses_dialect_safe_cast():
    module = _load_migration_module()
    statements = []

    class CaptureConnection:
        def execute(self, statement):
            statements.append(statement)

    module._backfill_legacy_namespace(CaptureConnection(), "nodes", "bridge_id")

    assert "AS CHAR(36)" in str(statements[0].compile(dialect=mysql.dialect()))
    assert "AS VARCHAR(36)" in str(statements[0].compile(dialect=postgresql.dialect()))


def test_namespace_migration_refuses_incomplete_backfill():
    module = _load_migration_module()

    class ConnectionWithLegacyWriter:
        @staticmethod
        def scalar(_statement):
            return 1

    with pytest.raises(RuntimeError, match="stop legacy writers"):
        module._assert_backfill_complete(ConnectionWithLegacyWriter(), "users", "sync_id")
