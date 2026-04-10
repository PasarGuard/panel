"""backfill wireguard keypairs in proxy_settings

Revision ID: f8a3c9d1e2b4
Revises: 6b7a1e8c2d14
Create Date: 2026-04-10 12:00:00.000000

"""

import json

import sqlalchemy as sa
from alembic import op

from app.models.proxy import ProxyTable
from app.utils.crypto import generate_wireguard_keypair, get_wireguard_public_key
from app.utils.proxy_settings import (
    dump_proxy_settings_for_storage,
    load_proxy_settings,
    normalize_proxy_settings_storage,
)


def _ensure_wireguard_keys(proxy_settings: ProxyTable) -> None:
    if proxy_settings.wireguard.public_key and not proxy_settings.wireguard.private_key:
        raise ValueError("wireguard private_key is required when user is assigned to a WireGuard interface")

    if not proxy_settings.wireguard.private_key:
        private_key, public_key = generate_wireguard_keypair()
        proxy_settings.wireguard.private_key = private_key
        proxy_settings.wireguard.public_key = public_key
    elif not proxy_settings.wireguard.public_key:
        proxy_settings.wireguard.public_key = get_wireguard_public_key(proxy_settings.wireguard.private_key)

revision = "f8a3c9d1e2b4"
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

        original_storage = normalize_proxy_settings_storage(proxy_settings)
        wireguard_settings = original_storage.get("wireguard") or {}
        needs_keypair_update = not wireguard_settings.get("private_key") or not wireguard_settings.get("public_key")
        if not needs_keypair_update:
            continue

        proxy_table = load_proxy_settings(original_storage)
        try:
            _ensure_wireguard_keys(proxy_table)
        except ValueError:
            # Invalid state (e.g. public_key without private_key); leave row unchanged.
            continue

        updates.append(
            {
                "_id": user_id,
                "proxy_settings": dump_proxy_settings_for_storage(proxy_table, original_storage),
            }
        )

    if updates:
        bind.execute(
            users_table.update().where(users_table.c.id == sa.bindparam("_id")),
            updates,
        )


def downgrade() -> None:
    # Keys cannot be distinguished from pre-migration data; do not strip wireguard keys.
    pass
