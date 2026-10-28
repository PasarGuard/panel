"""add client profiles

Revision ID: d1f3a5c7e9b2
Revises: c8d2e4f6a1b3
Create Date: 2026-10-23 00:00:00.000000

"""

import json

import sqlalchemy as sa
from alembic import op

from app.db.compiles_types import SqliteCompatibleBigInteger

revision = "d1f3a5c7e9b2"
down_revision = "c8d2e4f6a1b3"
branch_labels = None
depends_on = None

CLIENT_PROFILES_PERMISSIONS = {"create": True, "read": True, "read_simple": True, "update": True, "delete": True}
BUILTIN_ROLES_WITH_CLIENT_PROFILES = {"owner", "administrator"}


def _update_builtin_permissions(add_permission: bool) -> None:
    connection = op.get_bind()
    roles = sa.table(
        "admin_roles",
        sa.column("id", sa.BigInteger),
        sa.column("name", sa.String),
        sa.column("permissions", sa.JSON),
    )
    rows = connection.execute(sa.select(roles.c.id, roles.c.name, roles.c.permissions)).fetchall()

    for role_id, name, raw_permissions in rows:
        permissions = raw_permissions
        if isinstance(permissions, str):
            permissions = json.loads(permissions)
        permissions = dict(permissions or {})
        if add_permission:
            if name not in BUILTIN_ROLES_WITH_CLIENT_PROFILES or "client_profiles" in permissions:
                continue
            permissions["client_profiles"] = dict(CLIENT_PROFILES_PERMISSIONS)
        else:
            if "client_profiles" not in permissions:
                continue
            permissions.pop("client_profiles")
        connection.execute(roles.update().where(roles.c.id == role_id).values(permissions=permissions))


def upgrade() -> None:
    op.create_table(
        "client_profiles",
        sa.Column("id", SqliteCompatibleBigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("templates", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("settings", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_client_profiles")),
        sa.UniqueConstraint("name", name=op.f("uq_client_profiles_name")),
    )

    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("client_profile_id", SqliteCompatibleBigInteger(), nullable=True))
        batch_op.create_index(batch_op.f("ix_users_client_profile_id"), ["client_profile_id"], unique=False)
        batch_op.create_foreign_key(
            batch_op.f("fk_users_client_profile_id_client_profiles"),
            "client_profiles",
            ["client_profile_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("user_templates") as batch_op:
        batch_op.add_column(sa.Column("client_profile_id", SqliteCompatibleBigInteger(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_user_templates_client_profile_id_client_profiles"),
            "client_profiles",
            ["client_profile_id"],
            ["id"],
            ondelete="SET NULL",
        )

    _update_builtin_permissions(True)


def downgrade() -> None:
    _update_builtin_permissions(False)

    with op.batch_alter_table("user_templates") as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_user_templates_client_profile_id_client_profiles"), type_="foreignkey")
        batch_op.drop_column("client_profile_id")

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_users_client_profile_id_client_profiles"), type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_users_client_profile_id"))
        batch_op.drop_column("client_profile_id")

    op.drop_table("client_profiles")
