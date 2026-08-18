"""add cleanup retention settings

Revision ID: 7b3d1e9c4a6f
Revises: 6a9fff8290b9
Create Date: 2026-08-17 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

revision = "7b3d1e9c4a6f"
down_revision = "6a9fff8290b9"
branch_labels = None
depends_on = None

MAX_RETENTION_DAYS = 36_500


class MigrationSettings(BaseSettings):
    """Read the legacy retention value used to seed the new cleanup policy."""

    users_autodelete_days: int = Field(default=-1, validation_alias="USERS_AUTODELETE_DAYS")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


def normalize_legacy_retention_days(legacy_days: int) -> int | None:
    """Map legacy retention values into the range accepted by the runtime schema."""
    if legacy_days < 0:
        return None
    return min(legacy_days, MAX_RETENTION_DAYS)


def upgrade() -> None:
    """Add cleanup policies and indexes, preserving the legacy user setting."""
    legacy_days = MigrationSettings().users_autodelete_days
    default_cleanup = {
        "expired_users_retention_days": normalize_legacy_retention_days(legacy_days),
        "usage_history_retention_days": 90,
        "node_stats_retention_days": 30,
    }

    with op.batch_alter_table("settings", schema=None) as batch_op:
        batch_op.add_column(sa.Column("cleanup", sa.JSON(), nullable=True))

    settings_table = sa.table("settings", sa.column("cleanup", sa.JSON()))
    op.execute(settings_table.update().values(cleanup=default_cleanup))

    with op.batch_alter_table("settings", schema=None) as batch_op:
        batch_op.alter_column("cleanup", existing_type=sa.JSON(), nullable=False)

    with op.batch_alter_table("node_stats", schema=None) as batch_op:
        batch_op.create_index("ix_node_stats_created_at", ["created_at"], unique=False)
        batch_op.create_index("ix_node_stats_node_id_created_at", ["node_id", "created_at"], unique=False)


def downgrade() -> None:
    """Remove cleanup policies and their supporting node-stat indexes."""
    with op.batch_alter_table("node_stats", schema=None) as batch_op:
        batch_op.drop_index("ix_node_stats_node_id_created_at")
        batch_op.drop_index("ix_node_stats_created_at")

    with op.batch_alter_table("settings", schema=None) as batch_op:
        batch_op.drop_column("cleanup")
