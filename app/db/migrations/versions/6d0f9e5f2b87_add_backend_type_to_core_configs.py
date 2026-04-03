"""add backend type to core configs

Revision ID: 6d0f9e5f2b87
Revises: 145c22ab174f
Create Date: 2026-04-02 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "6d0f9e5f2b87"
down_revision = "145c22ab174f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create the enum type for postgres explicitly
    core_type = sa.Enum("xray", "wireguard", "mtproto", "singbox", name="coretype")
    if op.get_bind().engine.name == "postgresql":
        core_type.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "core_configs",
        sa.Column("backend_type", core_type, nullable=False, server_default="xray"),
    )


def downgrade() -> None:
    op.drop_column("core_configs", "backend_type")
    # Drop the enum type for postgres if it exists
    if op.get_bind().engine.name == "postgresql":
        sa.Enum(name="coretype").drop(op.get_bind(), checkfirst=True)
