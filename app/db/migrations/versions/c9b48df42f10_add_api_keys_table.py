"""add api keys table

Revision ID: c9b48df42f10
Revises: f9c69a49f544
Create Date: 2026-05-25 00:00:00.000000

"""

import json

from alembic import op
import sqlalchemy as sa
import app.db.compiles_types


# revision identifiers, used by Alembic.
revision = "c9b48df42f10"
down_revision = "f9c69a49f544"
branch_labels = None
depends_on = None


OWNER_ADMIN_API_KEY_PERMS = {
    "create": True,
    "read": True,
    "read_simple": True,
    "update": True,
    "delete": True,
}

OPERATOR_API_KEY_PERMS = {
    "read": {"scope": 1},
    "read_simple": {"scope": 1},
    "update": {"scope": 1},
    "delete": {"scope": 1},
}


def _normalize_permissions(value):
    if value is None:
        return {}
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    if isinstance(value, dict):
        return value
    return {}


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", app.db.compiles_types.SqliteCompatibleBigInteger(), autoincrement=True, nullable=False),
        sa.Column("admin_id", app.db.compiles_types.SqliteCompatibleBigInteger(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("note", sa.String(length=512), nullable=True),
        sa.Column("key_hash", sa.String(length=128), nullable=False),
        sa.Column("api_key_trimmed", sa.String(length=16)),
        sa.Column("role_id", app.db.compiles_types.SqliteCompatibleBigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expire_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum("active", "disabled", name="apikeystatus"),
            nullable=False,
            server_default="active",
        ),
        sa.ForeignKeyConstraint(
            ["admin_id"], ["admins.id"], name=op.f("fk_api_keys_admin_id_admins"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["role_id"], ["admin_roles.id"], name=op.f("fk_api_keys_role_id_admin_roles")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_keys")),
        sa.UniqueConstraint("key_hash", name=op.f("uq_api_keys_key_hash")),
        sa.UniqueConstraint("admin_id", "name", name=op.f("uq_api_keys_admin_id")),
    )
    with op.batch_alter_table("api_keys", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_api_keys_admin_id"), ["admin_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_api_keys_created_at"), ["created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_api_keys_expire_date"), ["expire_date"], unique=False)

    conn = op.get_bind()
    admin_roles = sa.table(
        "admin_roles",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("permissions", sa.JSON),
    )

    rows = conn.execute(sa.select(admin_roles.c.id, admin_roles.c.name, admin_roles.c.permissions)).fetchall()
    for role_id, role_name, role_permissions in rows:
        permissions = _normalize_permissions(role_permissions)
        if "api_keys" in permissions:
            continue

        if role_name in {"owner", "administrator"}:
            permissions["api_keys"] = OWNER_ADMIN_API_KEY_PERMS
        else:
            permissions["api_keys"] = OPERATOR_API_KEY_PERMS

        conn.execute(admin_roles.update().where(admin_roles.c.id == role_id).values(permissions=permissions))


def downgrade() -> None:
    conn = op.get_bind()
    admin_roles = sa.table(
        "admin_roles",
        sa.column("id", sa.Integer),
        sa.column("permissions", sa.JSON),
    )

    rows = conn.execute(sa.select(admin_roles.c.id, admin_roles.c.permissions)).fetchall()
    for role_id, role_permissions in rows:
        permissions = _normalize_permissions(role_permissions)
        if "api_keys" not in permissions:
            continue
        permissions.pop("api_keys", None)
        conn.execute(admin_roles.update().where(admin_roles.c.id == role_id).values(permissions=permissions))

    with op.batch_alter_table("api_keys", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_api_keys_expire_date"))
        batch_op.drop_index(batch_op.f("ix_api_keys_created_at"))
        batch_op.drop_index(batch_op.f("ix_api_keys_admin_id"))

    op.drop_table("api_keys")

    # Drop the enum type for PostgreSQL
    if conn.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS apikeystatus")
