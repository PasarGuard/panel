"""Add optional node leaf certificate fingerprint.

Revision ID: f3a91b62d408
Revises: c7d2e9a4b1f3
"""

import sqlalchemy as sa
from alembic import op

revision = "f3a91b62d408"
down_revision = "c7d2e9a4b1f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("nodes", sa.Column("certificate_sha256", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("nodes", "certificate_sha256")
