import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.models.host import BaseHost, CreateHost


def test_host_schema_keeps_singbox_and_finalmask_without_legacy_xray_settings():
    for model in (BaseHost, CreateHost):
        schema = model.model_json_schema()
        assert "noise_settings" not in schema["properties"]
        assert "xray" not in schema["$defs"]["FragmentSettings"]["properties"]
        assert "sing_box" in schema["$defs"]["FragmentSettings"]["properties"]
        assert "final_mask_settings" in schema["properties"]


def test_migration_preserves_all_fragment_and_finalmask_settings(monkeypatch):
    path = Path("app/db/migrations/versions/d6e8a12c9b45_remove_legacy_host_noise.py")
    spec = importlib.util.spec_from_file_location("host_legacy_removal", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    hosts = sa.Table(
        "hosts",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("fragment_settings", sa.JSON(none_as_null=True)),
        sa.Column("noise_settings", sa.JSON(none_as_null=True)),
        sa.Column("final_mask_settings", sa.JSON(none_as_null=True)),
    )
    metadata.create_all(engine)
    singbox = {"fragment": True, "fragment_fallback_delay": "100ms", "record_fragment": True}
    xray = {"packets": "tlshello", "length": "10-20", "interval": "5-10"}
    finalmask = {"tcp": [{"type": "fragment", "settings": {"lengths": ["10-20"], "delays": ["5-10"]}}]}
    with engine.begin() as connection:
        connection.execute(
            hosts.insert(),
            [
                {
                    "id": index,
                    "fragment_settings": settings,
                    "noise_settings": {"xray": [{"type": "rand"}]},
                    "final_mask_settings": finalmask,
                }
                for index, settings in enumerate(
                    [
                        {"xray": xray},
                        {"xray": xray, "sing_box": singbox},
                        {"sing_box": singbox},
                        None,
                    ],
                    1,
                )
            ],
        )
        monkeypatch.setattr(module, "op", Operations(MigrationContext.configure(connection)))
        module.upgrade()
        upgraded = sa.Table("hosts", sa.MetaData(), autoload_with=connection)
        assert "noise_settings" not in upgraded.c
        rows = connection.execute(sa.select(upgraded).order_by(upgraded.c.id)).mappings().all()
        assert [row["fragment_settings"] for row in rows] == [
            {"xray": xray},
            {"xray": xray, "sing_box": singbox},
            {"sing_box": singbox},
            None,
        ]
        assert all(row["final_mask_settings"] == finalmask for row in rows)

        module.downgrade()
        restored = sa.Table("hosts", sa.MetaData(), autoload_with=connection)
        assert "noise_settings" in restored.c
        assert connection.execute(sa.select(restored.c.noise_settings)).scalars().all() == [None] * 4
