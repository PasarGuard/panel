"""fix alpn enum

Revision ID: f44ec4769d5d
Revises: 89bcb1419c66
Create Date: 2025-03-27 13:14:48.350098

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'f44ec4769d5d'
down_revision = '89bcb1419c66'
branch_labels = None
depends_on = None


old_enum_name = "alpn"
new_enum_name = "proxyhostalpn"
values = ('none', 'h3', 'h2', 'http/1.1', 'h3,h2,http/1.1', 'h3,h2', 'h2,http/1.1')

new_type = sa.Enum(*values, name=new_enum_name)


def upgrade():
    bind = op.get_bind()

    try:
        new_type.drop(bind, checkfirst=False)
    except Exception:
        pass
    
    if bind.dialect.name == "postgresql":
        # Rename the ENUM type directly in PostgreSQL
        op.execute(f"ALTER TYPE {old_enum_name} RENAME TO {new_enum_name};")
    else:
        # For SQLite/MySQL: No-op (ENUM name is irrelevant)
        pass

def downgrade():
    bind = op.get_bind()
    
    if bind.dialect.name == "postgresql":
        # Reverse the rename
        op.execute(f"ALTER TYPE {new_enum_name} RENAME TO {old_enum_name};")
    else:
        # For SQLite/MySQL: No-op
        pass