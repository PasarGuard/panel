"""add admin passkey credentials and WebAuthn challenges

Revision ID: 9a5c2e7f1b4d
Revises: 48a6bcb8bba1
"""

from alembic import op
import sqlalchemy as sa
from app.db.compiles_types import SqliteCompatibleBigInteger
from app.db.compiles_types import WebAuthnBinary


revision = "9a5c2e7f1b4d"
down_revision = "48a6bcb8bba1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_passkeys",
        sa.Column("id", SqliteCompatibleBigInteger(), autoincrement=True, nullable=False),
        sa.Column("admin_id", SqliteCompatibleBigInteger(), nullable=False),
        sa.Column("credential_id", WebAuthnBinary(1024), nullable=False),
        sa.Column("public_key", WebAuthnBinary(4096), nullable=False),
        sa.Column("sign_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("name", sa.String(length=128), nullable=False, server_default="Passkey"),
        sa.ForeignKeyConstraint(["admin_id"], ["admins.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("credential_id"),
    )
    op.create_table(
        "passkey_challenges",
        sa.Column("id", SqliteCompatibleBigInteger(), autoincrement=True, nullable=False),
        sa.Column("challenge", WebAuthnBinary(128), nullable=False),
        sa.Column("admin_id", SqliteCompatibleBigInteger(), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["admin_id"], ["admins.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("challenge"),
    )


def downgrade() -> None:
    op.drop_table("passkey_challenges")
    op.drop_table("admin_passkeys")
