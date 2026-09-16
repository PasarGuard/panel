"""add mcp settings and oauth clients

Revision ID: a7c3e9d1f0b2
Revises: 48a6bcb8bba1
Create Date: 2026-09-15 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a7c3e9d1f0b2"
down_revision = "48a6bcb8bba1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("admins") as batch_op:
        batch_op.add_column(sa.Column("mcp", sa.JSON(), nullable=True))

    with op.batch_alter_table("api_keys") as batch_op:
        batch_op.add_column(sa.Column("mcp", sa.JSON(), nullable=True))

    op.create_table(
        "mcp_oauth_clients",
        sa.Column("client_id", sa.String(length=36), nullable=False),
        sa.Column("client_name", sa.String(length=256), nullable=True),
        sa.Column("client_secret", sa.String(length=128), nullable=True),
        sa.Column("redirect_uris", sa.JSON(), nullable=False),
        sa.Column("grant_types", sa.JSON(), nullable=False),
        sa.Column("token_endpoint_auth_method", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("client_id"),
    )


def downgrade() -> None:
    op.drop_table("mcp_oauth_clients")
    with op.batch_alter_table("api_keys") as batch_op:
        batch_op.drop_column("mcp")
    with op.batch_alter_table("admins") as batch_op:
        batch_op.drop_column("mcp")
