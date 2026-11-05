"""passkey_challenges expires_at index

Revision ID: d3f1a2b4c5e6
Revises: c8d2e4f6a1b3
Create Date: 2026-10-25

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "d3f1a2b4c5e6"
down_revision = "c8d2e4f6a1b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Every passkey options request purges expired challenges; index expires_at so that delete
    # does not scan the whole table.
    op.create_index(
        "ix_passkey_challenges_expires_at",
        "passkey_challenges",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_passkey_challenges_expires_at", table_name="passkey_challenges")
