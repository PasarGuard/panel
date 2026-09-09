"""merge the dev and node ordering migration heads

Revision ID: b7f4e6d9a1c2
Revises: d73f8a2c4e91, 8e2f1a9c4b70
Create Date: 2026-09-09 00:00:00.000000

"""

revision = "b7f4e6d9a1c2"
down_revision = ("d73f8a2c4e91", "8e2f1a9c4b70")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Merge the two parent migration branches without changing the schema."""


def downgrade() -> None:
    """Re-expose both parent heads when downgrading past the merge point."""
