"""fix user status enum

Revision ID: 89bcb1419c66
Revises: 1f6e978be88e
Create Date: 2025-03-27 12:03:01.459307

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '89bcb1419c66'
down_revision = '1f6e978be88e'
branch_labels = None
depends_on = None


old_enum_name = "status"
new_enum_name = "userstatus"
temp_enum_name = f"temp_{old_enum_name}"
values = ("active", "disabled", "limited", "expired", "on_hold")

old_type = sa.Enum(*values, name=old_enum_name)
new_type = sa.Enum(*values, name=new_enum_name)
temp_type = sa.Enum(*values, name=temp_enum_name)


# Describing of table
table_name = "users"
column_name = "status"
temp_table = sa.sql.table(
    table_name,
    sa.Column(
        column_name,
        new_type,
        nullable=False
    )
)


def upgrade():
    # temp type to use instead of old one
    try:
        new_type.drop(op.get_bind(), checkfirst=False)
    except Exception:
        pass

    temp_type.create(op.get_bind(), checkfirst=False)

    # changing of column type from old enum to new one.
    # SQLite will create temp table for this
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.alter_column(
            column_name,
            existing_type=old_type,
            type_=temp_type,
            existing_nullable=False,
            postgresql_using=f"{column_name}::text::{temp_enum_name}"
        )

    # remove old enum, create new enum
    old_type.drop(op.get_bind(), checkfirst=False)
    new_type.create(op.get_bind(), checkfirst=False)

    # changing of column type from temp enum to new one.
    # SQLite will create temp table for this
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.alter_column(
            column_name,
            existing_type=temp_type,
            type_=new_type,
            existing_nullable=False,
            postgresql_using=f"{column_name}::text::{new_enum_name}"
        )

    # remove temp enum
    temp_type.drop(op.get_bind(), checkfirst=False)


def downgrade():
    temp_type.create(op.get_bind(), checkfirst=False)

    with op.batch_alter_table(table_name) as batch_op:
        batch_op.alter_column(
            column_name,
            existing_type=new_type,
            type_=temp_type,
            existing_nullable=False,
            postgresql_using=f"{column_name}::text::{temp_enum_name}"
        )

    new_type.drop(op.get_bind(), checkfirst=False)
    old_type.create(op.get_bind(), checkfirst=False)

    with op.batch_alter_table(table_name) as batch_op:
        batch_op.alter_column(
            column_name,
            existing_type=temp_type,
            type_=old_type,
            existing_nullable=False,
            postgresql_using=f"{column_name}::text::{old_enum_name}"
        )

    temp_type.drop(op.get_bind(), checkfirst=False)
