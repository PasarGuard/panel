import importlib.util
from pathlib import Path

import sqlalchemy as sa


def _load_migration_module():
    path = Path("app/db/migrations/versions/a8c2d491e705_bind_xray_client_inbounds_to_loopback.py")
    spec = importlib.util.spec_from_file_location("xray_loopback_migration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_xray_loopback_migration_updates_edited_system_template_without_reformatting(monkeypatch):
    module = _load_migration_module()
    canonical = '{"inbounds": [{"listen": "0.0.0.0"}]}'
    customized = (
        '{"inbounds":[{"listen":"0.0.0.0", "custom": true}], '
        '"outbounds": [{"listen": "0.0.0.0"}], "label": "keep 0.0.0.0"}'
    )
    already_safe = '{"inbounds": [{"listen": "127.0.0.1", "custom": true}]}'

    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    templates = sa.Table(
        "client_templates",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("template_type", sa.String),
        sa.Column("content", sa.Text),
        sa.Column("is_system", sa.Boolean),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            templates.insert(),
            [
                {"id": 1, "template_type": "xray_subscription", "content": canonical, "is_system": True},
                {"id": 2, "template_type": "xray_subscription", "content": customized, "is_system": True},
                {"id": 3, "template_type": "xray_subscription", "content": customized, "is_system": False},
                {"id": 4, "template_type": "singbox_subscription", "content": customized, "is_system": True},
                {"id": 5, "template_type": "xray_subscription", "content": already_safe, "is_system": True},
            ],
        )
        monkeypatch.setattr(module.op, "get_bind", lambda: connection)

        module.upgrade()

        contents = dict(connection.execute(sa.select(templates.c.id, templates.c.content)).all())

    assert contents[1] == '{"inbounds": [{"listen": "127.0.0.1"}]}'
    assert contents[2] == (
        '{"inbounds":[{"listen":"127.0.0.1", "custom": true}], '
        '"outbounds": [{"listen": "0.0.0.0"}], "label": "keep 0.0.0.0"}'
    )
    assert contents[3] == customized
    assert contents[4] == customized
    assert contents[5] == already_safe
