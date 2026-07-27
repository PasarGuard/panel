"""add unique constraint to admin notification reminders

Revision ID: fb32155473c1
Revises: 3c1a7e5b9d20
Create Date: 2026-07-26 19:32:42.096475

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fb32155473c1'
down_revision = '3c1a7e5b9d20'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Update any existing NULL thresholds to 0
    op.execute(
        "UPDATE admin_notification_reminders SET threshold = 0 WHERE threshold IS NULL"
    )

    # 2. Clean up duplicate rows before creating the constraint
    op.execute(
        """
        DELETE FROM admin_notification_reminders
        WHERE id NOT IN (
            SELECT min_id FROM (
                SELECT MIN(id) AS min_id
                FROM admin_notification_reminders
                GROUP BY admin_id, type, threshold
            ) AS temp
        )
        """
    )

    # 3. Alter threshold column to be non-nullable with a server default of 0 and create the constraint
    with op.batch_alter_table("admin_notification_reminders", schema=None) as batch_op:
        batch_op.alter_column(
            "threshold",
            existing_type=sa.Integer(),
            nullable=False,
            server_default="0"
        )
        batch_op.create_unique_constraint(
            "uq_admin_notification_reminders_admin_id_type_threshold",
            ["admin_id", "type", "threshold"]
        )


def downgrade() -> None:
    with op.batch_alter_table("admin_notification_reminders", schema=None) as batch_op:
        batch_op.drop_constraint(
            "uq_admin_notification_reminders_admin_id_type_threshold",
            type_="unique"
        )
        batch_op.alter_column(
            "threshold",
            existing_type=sa.Integer(),
            nullable=True,
            server_default=None
        )
