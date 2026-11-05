"""The migration that moves the EXTERNAL_CONFIG env var into the subscription.external_links setting."""

import importlib.util
import json
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.models.settings import Subscription

MIGRATION = (
    Path(__file__).resolve().parents[1] / "app/db/migrations/versions/e44109df0cc6_move_external_config_to_settings.py"
)
VLESS = "vless://c90cff8e-d651-414e-8e83-1a187622d957@203.0.113.10:443?security=reality#A"
TROJAN = "trojan://secret@203.0.113.11:443?security=tls#B"
SS = "ss://YWVzLTEyOC1nY206cGFzcw@203.0.113.12:8388#C"


@pytest.fixture(scope="module")
def migration():
    spec = importlib.util.spec_from_file_location("move_external_config_to_settings", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_reads_environment_before_dotenv_in_any_case(migration):
    assert migration.read_env_links(environ={"external_config": f" {VLESS}\n{TROJAN} "}, dotenv={}) == [VLESS, TROJAN]
    assert migration.read_env_links(environ={}, dotenv={"External_Config": SS}) == [SS]
    assert migration.read_env_links(environ={"EXTERNAL_CONFIG": ""}, dotenv={"EXTERNAL_CONFIG": SS}) == []
    assert migration.read_env_links(environ={"PATH": "/bin"}, dotenv={}) == []


def test_migration_reads_dotenv_file(migration, tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(f'# comment\nEXTERNAL_CONFIG = "{VLESS} {SS}"\n')
    monkeypatch.chdir(tmp_path)

    assert migration.read_env_links(environ={}) == [VLESS, SS]


def test_migration_appends_links_after_stored_ones_without_duplicates(migration):
    stored = {"rules": [], "external_links": [TROJAN, VLESS]}

    subscription = migration.add_links(stored, [VLESS, SS, SS])

    assert subscription == {"rules": [], "external_links": [TROJAN, VLESS, SS]}
    # The stored section is not changed in place
    assert stored == {"rules": [], "external_links": [TROJAN, VLESS]}
    assert Subscription.model_validate(subscription).external_links == [TROJAN, VLESS, SS]
    assert migration.add_links({"rules": []}, [VLESS]) == {"rules": [], "external_links": [VLESS]}


def test_migration_downgrade_removes_only_the_env_links(migration):
    assert migration.remove_links({"rules": [], "external_links": [TROJAN, VLESS, SS]}, [VLESS, SS]) == {
        "rules": [],
        "external_links": [TROJAN],
    }
    assert migration.remove_links({"rules": [], "external_links": [VLESS]}, [VLESS]) == {"rules": []}
    assert migration.remove_links({"rules": []}, [VLESS]) == {"rules": []}


def _engine(subscription: dict) -> sa.Engine:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE settings (id INTEGER PRIMARY KEY, subscription JSON NOT NULL)"))
        conn.execute(
            sa.text("INSERT INTO settings (id, subscription) VALUES (1, :value)"), {"value": json.dumps(subscription)}
        )
    return engine


def _run(engine: sa.Engine, migration, step: str) -> dict:
    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        getattr(migration, step)()
    with engine.connect() as conn:
        return json.loads(conn.execute(sa.text("SELECT subscription FROM settings WHERE id = 1")).scalar_one())


def test_migration_upgrade_and_downgrade_on_the_settings_row(migration, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EXTERNAL_CONFIG", f"{VLESS} {SS}")
    engine = _engine({"rules": [], "external_links": [TROJAN]})

    assert _run(engine, migration, "upgrade") == {"rules": [], "external_links": [TROJAN, VLESS, SS]}
    # Running it again adds nothing
    assert _run(engine, migration, "upgrade") == {"rules": [], "external_links": [TROJAN, VLESS, SS]}
    assert _run(engine, migration, "downgrade") == {"rules": [], "external_links": [TROJAN]}


def test_migration_without_env_value_leaves_the_settings_row(migration, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EXTERNAL_CONFIG", raising=False)
    engine = _engine({"rules": [], "external_links": [TROJAN]})

    assert _run(engine, migration, "upgrade") == {"rules": [], "external_links": [TROJAN]}
    assert _run(engine, migration, "downgrade") == {"rules": [], "external_links": [TROJAN]}
