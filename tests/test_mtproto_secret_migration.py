import importlib.util
import json
import re
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

_MIGRATION = Path("app/db/migrations/versions/d5e1f3a7b9c2_add_mtproto_secret_to_proxy_settings.py")
_HEX32 = re.compile(r"[0-9a-fA-F]{32}")
_NULL = object()


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("mtproto_secret_migration", _MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _engine(rows: list) -> sa.Engine:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE users (id INTEGER PRIMARY KEY, proxy_settings JSON)"))
        conn.execute(
            sa.text("INSERT INTO users (id, proxy_settings) VALUES (:id, :settings)"),
            [
                {"id": index, "settings": None if row is _NULL else json.dumps(row)}
                for index, row in enumerate(rows, start=1)
            ],
        )
    return engine


def _run(engine: sa.Engine, step: str) -> None:
    module = _load_migration_module()
    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        getattr(module, step)()


def _raw(engine: sa.Engine) -> dict[int, str | None]:
    with engine.connect() as conn:
        return dict(conn.execute(sa.text("SELECT id, proxy_settings FROM users ORDER BY id")).all())


def _settings(engine: sa.Engine) -> dict[int, dict]:
    return {row_id: json.loads(raw) for row_id, raw in _raw(engine).items()}


_ROWS = [
    {"vless": {"id": "x"}},
    {"mtproto": {"secret": "", "max_tcp_conns": 3}},
    {"mtproto": {"secret": "AA" * 16}},
    {"mtproto": {"secret": "zz"}},
    {"mtproto": "broken"},
    "not-an-object",
    _NULL,
    {"mtproto": {"secret": "zz" * 16}},
]


def test_upgrade_backfills_missing_and_invalid_secrets():
    engine = _engine(_ROWS)
    before = _raw(engine)

    _run(engine, "upgrade")

    after = _raw(engine)
    settings = _settings(engine)
    assert after[3] == before[3]
    for row_id, row in settings.items():
        assert isinstance(row, dict), row_id
        secret = row["mtproto"]["secret"]
        assert isinstance(secret, str) and _HEX32.fullmatch(secret), row_id
        assert "user_ad_tag" not in row["mtproto"], row_id
    assert settings[1]["vless"] == {"id": "x"}
    assert settings[2]["mtproto"]["max_tcp_conns"] == 3
    assert settings[8]["mtproto"]["secret"] != "zz" * 16
    new_secrets = [row["mtproto"]["secret"] for row_id, row in settings.items() if row_id != 3]
    assert all(re.fullmatch(r"[0-9a-f]{32}", secret) for secret in new_secrets)
    assert len(set(new_secrets)) == len(new_secrets)


def test_upgrade_pages_through_more_than_one_batch():
    engine = _engine([{} for _ in range(2500)])

    _run(engine, "upgrade")

    secrets = [row["mtproto"]["secret"] for row in _settings(engine).values()]
    assert len(secrets) == 2500
    assert all(_HEX32.fullmatch(secret) for secret in secrets)
    assert len(set(secrets)) == 2500


def test_downgrade_removes_secrets_only():
    engine = _engine(_ROWS)

    _run(engine, "upgrade")
    _run(engine, "downgrade")

    settings = _settings(engine)
    for row_id, row in settings.items():
        assert "secret" not in row.get("mtproto", {}), row_id
    assert settings[1]["vless"] == {"id": "x"}
    assert settings[2]["mtproto"]["max_tcp_conns"] == 3
