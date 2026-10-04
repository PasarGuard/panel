"""Preserve subscription token timestamp microseconds.

Apply this migration before deploying code that issues v5 tokens. On rollback,
deploy the predecessor application before downgrading this revision. Existing
v5 tokens fail closed after ``created_at`` precision is reduced and must be
reissued.

Revision ID: 9e0d7a1c4b52
Revises: 8e2f1a9c4b70
Create Date: 2026-08-09

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "9e0d7a1c4b52"
down_revision = "8e2f1a9c4b70"
branch_labels = None
depends_on = None


def _is_mysql_family() -> bool:
    return op.get_bind().dialect.name in {"mysql", "mariadb"}


def upgrade() -> None:
    if _is_mysql_family():
        op.alter_column(
            "users",
            "created_at",
            existing_type=mysql.DATETIME(fsp=0),
            type_=mysql.DATETIME(fsp=6),
            existing_nullable=False,
        )
        op.alter_column(
            "users",
            "sub_revoked_at",
            existing_type=mysql.DATETIME(fsp=0),
            type_=mysql.DATETIME(fsp=6),
            existing_nullable=True,
        )


def _ceil_revocations_before_precision_loss() -> None:
    # Truncating a revocation down can resurrect a token issued later in the
    # same second. Round it up before DATETIME(6) -> DATETIME(0) instead.
    op.execute(
        sa.text(
            """
            UPDATE users
            SET sub_revoked_at = DATE_ADD(
                DATE_SUB(sub_revoked_at, INTERVAL MICROSECOND(sub_revoked_at) MICROSECOND),
                INTERVAL IF(MICROSECOND(sub_revoked_at) = 0, 0, 1) SECOND
            )
            WHERE sub_revoked_at IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    if _is_mysql_family():
        _ceil_revocations_before_precision_loss()
        op.alter_column(
            "users",
            "sub_revoked_at",
            existing_type=mysql.DATETIME(fsp=6),
            type_=mysql.DATETIME(fsp=0),
            existing_nullable=True,
        )
        op.alter_column(
            "users",
            "created_at",
            existing_type=mysql.DATETIME(fsp=6),
            type_=mysql.DATETIME(fsp=0),
            existing_nullable=False,
        )
