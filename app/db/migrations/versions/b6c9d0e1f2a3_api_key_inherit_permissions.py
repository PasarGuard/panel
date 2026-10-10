"""api key inherit permissions

Revision ID: b6c9d0e1f2a3
Revises: 9aa99aaee80f
Create Date: 2026-06-19 20:30:00.000000

"""

import json

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b6c9d0e1f2a3"
down_revision = "9aa99aaee80f"
branch_labels = None
depends_on = None


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
    with op.batch_alter_table("api_keys", schema=None) as batch_op:
        batch_op.add_column(sa.Column("inherit_permissions", sa.Boolean(), nullable=False, server_default="1"))

    conn = op.get_bind()
    admin_roles = sa.table(
        "admin_roles",
        sa.column("id", sa.Integer),
        sa.column("permissions", sa.JSON),
    )

    rows = conn.execute(sa.select(admin_roles.c.id, admin_roles.c.permissions)).fetchall()
    for role_id, role_permissions in rows:
        permissions = _normalize_permissions(role_permissions)
        api_key_permissions = permissions.get("api_keys")
        if not isinstance(api_key_permissions, dict):
            continue

        changed = False
        for action in ("read", "read_simple", "update", "delete"):
            if api_key_permissions.get(action) is True:
                api_key_permissions[action] = {"scope": 2}
                changed = True

        if changed:
            permissions["api_keys"] = api_key_permissions
            conn.execute(admin_roles.update().where(admin_roles.c.id == role_id).values(permissions=permissions))


def downgrade() -> None:
    with op.batch_alter_table("api_keys", schema=None) as batch_op:
        batch_op.drop_column("inherit_permissions")
