"""add MASQUE auth and DNS settings to proxy settings

Revision ID: c8d2e4f6a1b3
Revises: a8c2d491e705
Create Date: 2026-10-12 00:00:00.000000

"""
import json
from secrets import token_urlsafe

import sqlalchemy as sa
from alembic import op

revision = "c8d2e4f6a1b3"
down_revision = "a8c2d491e705"
branch_labels = None
depends_on = None


def _masque_password(users_table, dialect: str):
    """Return a SQL expression extracting the stored MASQUE password.

    Support PostgreSQL, MySQL, and SQLite; raise ``RuntimeError`` for other
    dialects. This builds an expression without executing a query.
    """
    settings = users_table.c.proxy_settings
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import JSONB

        return sa.func.jsonb_extract_path_text(sa.cast(settings, JSONB), "masque", "password")
    if dialect == "mysql":
        return sa.func.json_unquote(sa.func.json_extract(settings, "$.masque.password"))
    if dialect == "sqlite":
        return sa.func.json_extract(settings, "$.masque.password")
    raise RuntimeError(f"Unsupported database dialect: {dialect}")


def upgrade() -> None:
    """Fill missing or empty MASQUE passwords for users with positive IDs.

    Generate a separate URL-safe password from 24 random bytes for each user,
    processing up to 1,000 users per batch. Keep existing nonempty passwords
    and other settings in mappings; replace non-mapping settings with mappings.
    Unsupported dialects raise ``RuntimeError``. JSON decoding and database
    errors propagate.
    """
    bind = op.get_bind()
    dialect = bind.dialect.name
    users_table = sa.table(
        "users",
        sa.column("id", sa.Integer),
        sa.column("proxy_settings", sa.JSON),
    )
    password = _masque_password(users_table, dialect)
    missing_password = sa.or_(password.is_(None), password == "")
    update = users_table.update().where(users_table.c.id == sa.bindparam("_id")).values(
        proxy_settings=sa.bindparam("_settings_value", type_=sa.JSON)
    )

    # Passwords must be independently generated per user, so update only rows
    # that need one and process them in bounded batches.
    last_id = 0
    while True:
        users = bind.execute(
            sa.select(users_table.c.id, users_table.c.proxy_settings)
            .where(users_table.c.id > last_id, missing_password)
            .order_by(users_table.c.id)
            .limit(1000)
        ).fetchall()
        if not users:
            break

        updates = []
        for user_id, proxy_settings in users:
            last_id = user_id
            if isinstance(proxy_settings, str):
                proxy_settings = json.loads(proxy_settings)
            if not isinstance(proxy_settings, dict):
                proxy_settings = {}

            masque = proxy_settings.get("masque")
            if not isinstance(masque, dict):
                masque = {}
            masque["password"] = token_urlsafe(24)
            proxy_settings["masque"] = masque
            updates.append({"_id": user_id, "_settings_value": proxy_settings})

        bind.execute(update, updates)


def downgrade() -> None:
    """Remove stored MASQUE passwords, including those predating this migration.

    Preserve other settings and leave the containing MASQUE object in place.
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
    password = _masque_password(users_table, dialect)

    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import ARRAY, JSONB

        path = sa.literal_column("'{masque,password}'", type_=ARRAY(sa.Text()))
        updated_settings = sa.cast(settings, JSONB).op("#-")(path)
    elif dialect in ("mysql", "sqlite"):
        updated_settings = sa.func.json_remove(settings, "$.masque.password")
    else:
        raise RuntimeError(f"Unsupported database dialect: {dialect}")

    bind.execute(
        users_table.update()
        .where(sa.or_(password.is_not(None), password == ""))
        .values(proxy_settings=updated_settings)
    )
