"""add hwid policy to admin roles

Revision ID: 2c6e9d34a1f0
Revises: bb4a32b7f5ce
Create Date: 2026-05-22 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2c6e9d34a1f0"
down_revision = "bb4a32b7f5ce"
branch_labels = None
depends_on = None

def upgrade() -> None:
    with op.batch_alter_table("admin_roles", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "hwid",
                sa.JSON(),
                nullable=True,
            )
        )

    # Cross-dialect safe JSON initialization (SQLite/MySQL/PostgreSQL)
    admin_roles = sa.table(
        "admin_roles",
        sa.column("hwid", sa.JSON()),
    )
    op.execute(
        admin_roles.update()
        .where(admin_roles.c.hwid.is_(None))
        .values(
            hwid={
                "enabled": True,
                "forced": False,
                "fallback_limit": None,
                "min_limit": None,
                "max_limit": None,
            }
        )
    )

    with op.batch_alter_table("admin_roles", schema=None) as batch_op:
        batch_op.alter_column("hwid", existing_type=sa.JSON(), type_=sa.JSON(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("admin_roles", schema=None) as batch_op:
        batch_op.drop_column("hwid")
