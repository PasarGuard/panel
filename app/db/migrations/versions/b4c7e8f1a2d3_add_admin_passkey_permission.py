"""add admin passkey management permission

Revision ID: b4c7e8f1a2d3
Revises: 9a5c2e7f1b4d
"""

import json

import sqlalchemy as sa
from alembic import op


revision = "b4c7e8f1a2d3"
down_revision = "9a5c2e7f1b4d"
branch_labels = None
depends_on = None


def _update_builtin_permissions(add_permission: bool) -> None:
    connection = op.get_bind()
    roles = sa.table(
        "admin_roles",
        sa.column("id", sa.BigInteger),
        sa.column("name", sa.String),
        sa.column("permissions", sa.JSON),
    )
    builtin_names = {"owner", "administrator"}
    rows = connection.execute(sa.select(roles.c.id, roles.c.name, roles.c.permissions)).fetchall()

    for role_id, name, raw_permissions in rows:
        if name not in builtin_names:
            continue
        permissions = raw_permissions
        if isinstance(permissions, str):
            permissions = json.loads(permissions)
        permissions = dict(permissions or {})
        admins_permissions = dict(permissions.get("admins") or {})
        if add_permission:
            admins_permissions["passkeys"] = True
        else:
            admins_permissions.pop("passkeys", None)
        if admins_permissions:
            permissions["admins"] = admins_permissions
        else:
            permissions.pop("admins", None)
        connection.execute(
            roles.update().where(roles.c.id == role_id).values(permissions=permissions)
        )


def upgrade() -> None:
    _update_builtin_permissions(True)


def downgrade() -> None:
    _update_builtin_permissions(False)
