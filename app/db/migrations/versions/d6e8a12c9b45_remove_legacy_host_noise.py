"""Remove the legacy host noise column.

Revision ID: d6e8a12c9b45
Revises: f3a91b62d408

Existing configurations must be migrated to FinalMask before upgrading.
Stored fragment settings are left unchanged.
Downgrading restores the noise column, but cannot recover the removed noise settings.
"""

import sqlalchemy as sa
from alembic import op

revision = "d6e8a12c9b45"
down_revision = "f3a91b62d408"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("hosts", "noise_settings")


def downgrade() -> None:
    op.add_column("hosts", sa.Column("noise_settings", sa.JSON(none_as_null=True), nullable=True))
