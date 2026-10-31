"""add MTProto user secrets to proxy settings

Revision ID: d5e1f3a7b9c2
Revises: c8d2e4f6a1b3
Create Date: 2026-10-20 00:00:00.000000

"""
import json
import re
import secrets

import sqlalchemy as sa
from alembic import op

revision = "d5e1f3a7b9c2"
down_revision = "c8d2e4f6a1b3"
branch_labels = None
depends_on = None

_SECRET_RE = re.compile(r"[0-9a-fA-F]{32}")


def _mtproto_secret(users_table, dialect: str):
    """Return a SQL expression extracting the stored MTProto secret.

    Support PostgreSQL, MySQL, and SQLite; raise ``RuntimeError`` for other
    dialects. This builds an expression without executing a query.
    """
    settings = users_table.c.proxy_settings
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import JSONB

        return sa.func.jsonb_extract_path_text(sa.cast(settings, JSONB), "mtproto", "secret")
    if dialect == "mysql":
        return sa.func.json_unquote(sa.func.json_extract(settings, "$.mtproto.secret"))
    if dialect == "sqlite":
        return sa.func.json_extract(settings, "$.mtproto.secret")
    raise RuntimeError(f"Unsupported database dialect: {dialect}")


def upgrade() -> None:
    """Give every user with a positive ID a valid MTProto secret.

    Users whose stored secret is already 32 hex characters keep it byte for
    byte. Every other user gets ``secrets.token_hex(16)``, generated per user
    (the same source as ``app.models.proxy.generate_mtproto_secret``; migrations
    must not import app code, so change both together). All users are paged by
    ID, 1,000 per batch, and checked in Python rather than filtered by secret
    length in SQL, so a 32-character secret that is not hex is replaced too.
    Other settings and other MTProto keys are kept, and no defaults are written
    for the policy fields. Settings that are not a mapping (or text that does
    not parse as JSON) become mappings. Database errors propagate.
    """
    bind = op.get_bind()
    users_table = sa.table(
        "users",
        sa.column("id", sa.Integer),
        sa.column("proxy_settings", sa.JSON),
    )
    update = users_table.update().where(users_table.c.id == sa.bindparam("_id")).values(
        proxy_settings=sa.bindparam("_settings_value", type_=sa.JSON)
    )

    last_id = 0
    while True:
        users = bind.execute(
            sa.select(users_table.c.id, users_table.c.proxy_settings)
            .where(users_table.c.id > last_id)
            .order_by(users_table.c.id)
            .limit(1000)
        ).fetchall()
        if not users:
            break

        updates = []
        for user_id, proxy_settings in users:
            last_id = user_id
            if isinstance(proxy_settings, str):
                # A driver may hand back the raw text.
                try:
                    proxy_settings = json.loads(proxy_settings)
                except ValueError:
                    proxy_settings = {}
            if not isinstance(proxy_settings, dict):
                proxy_settings = {}

            mtproto = proxy_settings.get("mtproto")
            if not isinstance(mtproto, dict):
                mtproto = {}
            secret = mtproto.get("secret")
            if isinstance(secret, str) and _SECRET_RE.fullmatch(secret):
                continue

            mtproto["secret"] = secrets.token_hex(16)
            proxy_settings["mtproto"] = mtproto
            updates.append({"_id": user_id, "_settings_value": proxy_settings})

        if updates:
            bind.execute(update, updates)


def downgrade() -> None:
    """Remove stored MTProto secrets, including those predating this migration.

    Preserve other settings and leave the containing MTProto object in place.
    Unsupported dialects raise ``RuntimeError``; database errors propagate.
    """
    bind = op.get_bind()
    dialect = bind.dialect.name
    users_table = sa.table(
        "users",
        sa.column("id", sa.Integer),
        sa.column("proxy_settings", sa.JSON),
    )
    settings = users_table.c.proxy_settings
    secret = _mtproto_secret(users_table, dialect)

    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import ARRAY, JSONB

        path = sa.literal_column("'{mtproto,secret}'", type_=ARRAY(sa.Text()))
        updated_settings = sa.cast(settings, JSONB).op("#-")(path)
    elif dialect in ("mysql", "sqlite"):
        updated_settings = sa.func.json_remove(settings, "$.mtproto.secret")
    else:
        raise RuntimeError(f"Unsupported database dialect: {dialect}")

    bind.execute(users_table.update().where(secret.is_not(None)).values(proxy_settings=updated_settings))
