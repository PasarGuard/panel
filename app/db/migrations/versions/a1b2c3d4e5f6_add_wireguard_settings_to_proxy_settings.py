"""add wireguard settings to proxy_settings

Revision ID: a1b2c3d4e5f6
Revises: 6b7a1e8c2d14
Create Date: 2026-04-10 00:00:00.000000

"""
import json

import sqlalchemy as sa
from alembic import op

from app.utils.crypto import generate_wireguard_keypair, get_wireguard_public_key

revision = "a1b2c3d4e5f6"
down_revision = "6b7a1e8c2d14"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    users_table = sa.table(
        "users",
        sa.column("id", sa.Integer),
        sa.column("proxy_settings", sa.JSON),
    )

    users = bind.execute(sa.select(users_table.c.id, users_table.c.proxy_settings)).fetchall()

    updates = []
    for user_id, proxy_settings in users:
        if isinstance(proxy_settings, str):
            proxy_settings = json.loads(proxy_settings)
        if not proxy_settings:
            proxy_settings = {}

        wg = proxy_settings.get("wireguard")
        if not isinstance(wg, dict):
            wg = {}
        changed = False
        if not wg.get("private_key"):
            priv, pub = generate_wireguard_keypair()
            wg["private_key"] = priv
            wg["public_key"] = pub
            changed = True
        elif not wg.get("public_key"):
            wg["public_key"] = get_wireguard_public_key(wg["private_key"])
            changed = True
        if changed:
            proxy_settings["wireguard"] = wg
            updates.append({"_id": user_id, "proxy_settings": proxy_settings})

    if updates:
        bind.execute(
            users_table.update().where(users_table.c.id == sa.bindparam("_id")),
            updates,
        )


def downgrade() -> None:
    bind = op.get_bind()

    users_table = sa.table(
        "users",
        sa.column("id", sa.Integer),
        sa.column("proxy_settings", sa.JSON),
    )

    users = bind.execute(sa.select(users_table.c.id, users_table.c.proxy_settings)).fetchall()

    updates = []
    for user_id, proxy_settings in users:
        if isinstance(proxy_settings, str):
            proxy_settings = json.loads(proxy_settings)
        if proxy_settings and "wireguard" in proxy_settings:
            proxy_settings.pop("wireguard")
            updates.append({"_id": user_id, "proxy_settings": json.dumps(proxy_settings)})

    if updates:
        bind.execute(
            users_table.update().where(users_table.c.id == sa.bindparam("_id")),
            updates,
        )
