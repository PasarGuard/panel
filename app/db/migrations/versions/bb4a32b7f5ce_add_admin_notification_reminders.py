"""add admin notification reminders

Revision ID: bb4a32b7f5ce
Revises: a1d3f5b7c9e2
Create Date: 2026-05-19 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "bb4a32b7f5ce"
down_revision = "a1d3f5b7c9e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    reminder_type = (
        postgresql.ENUM("expiration_date", "data_usage", name="remindertype", create_type=False)
        if dialect == "postgresql"
        else sa.Enum("expiration_date", "data_usage", name="remindertype")
    )

    op.create_table(
        "admin_notification_reminders",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("admin_id", sa.BigInteger(), nullable=False),
        sa.Column("type", reminder_type, nullable=False),
        sa.Column("threshold", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["admin_id"], ["admins.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_admin_notification_reminders_admin_id_type",
        "admin_notification_reminders",
        ["admin_id", "type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_admin_notification_reminders_admin_id_type", table_name="admin_notification_reminders")
    op.drop_table("admin_notification_reminders")
