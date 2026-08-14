"""add user list sort index

Revision ID: b7e2c4d91f60
Revises: 6a9fff8290b9
Create Date: 2026-08-14 18:30:00.000000

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "b7e2c4d91f60"
down_revision = "6a9fff8290b9"
branch_labels = None
depends_on = None


INDEX_NAME = "idx_users_created_at_id"


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        # Keep user writes available while large installations build the index.
        with op.get_context().autocommit_block():
            op.create_index(
                INDEX_NAME,
                "users",
                ["created_at", "id"],
                unique=False,
                postgresql_concurrently=True,
            )
        return

    op.create_index(INDEX_NAME, "users", ["created_at", "id"], unique=False)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.drop_index(
                INDEX_NAME,
                table_name="users",
                postgresql_concurrently=True,
            )
        return

    op.drop_index(INDEX_NAME, table_name="users")
