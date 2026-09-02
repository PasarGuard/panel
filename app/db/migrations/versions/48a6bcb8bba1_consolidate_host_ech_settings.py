"""consolidate host ECH settings into JSON

Revision ID: 48a6bcb8bba1
Revises: 7c4bd5128e62
Create Date: 2026-09-02 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "48a6bcb8bba1"
down_revision = "7c4bd5128e62"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("hosts", sa.Column("ech", sa.JSON(), nullable=True))

    hosts = sa.table(
        "hosts",
        sa.column("id", sa.Integer()),
        sa.column("ech_config_list", sa.String(length=512)),
        sa.column("ech_query_strategy", sa.String(length=8)),
        sa.column("ech", sa.JSON()),
    )
    connection = op.get_bind()
    for row in connection.execute(
        sa.select(hosts.c.id, hosts.c.ech_config_list, hosts.c.ech_query_strategy)
    ).mappings():
        xray_ech = {
            key: value
            for key, value in {
                "config_list": row["ech_config_list"],
                "query_strategy": row["ech_query_strategy"],
            }.items()
            if value is not None
        }
        if xray_ech:
            connection.execute(hosts.update().where(hosts.c.id == row["id"]).values(ech={"xray": xray_ech}))

    op.drop_column("hosts", "ech_query_strategy")
    op.drop_column("hosts", "ech_config_list")


def downgrade() -> None:
    op.add_column("hosts", sa.Column("ech_config_list", sa.String(length=512), nullable=True))
    op.add_column("hosts", sa.Column("ech_query_strategy", sa.String(length=8), nullable=True))

    hosts = sa.table(
        "hosts",
        sa.column("id", sa.Integer()),
        sa.column("ech", sa.JSON()),
        sa.column("ech_config_list", sa.String(length=512)),
        sa.column("ech_query_strategy", sa.String(length=8)),
    )
    connection = op.get_bind()
    for row in connection.execute(sa.select(hosts.c.id, hosts.c.ech)).mappings():
        ech = row["ech"] if isinstance(row["ech"], dict) else {}
        xray_ech = ech.get("xray")
        xray_ech = xray_ech if isinstance(xray_ech, dict) else {}
        connection.execute(
            hosts.update()
            .where(hosts.c.id == row["id"])
            .values(
                ech_config_list=xray_ech.get("config_list"),
                ech_query_strategy=xray_ech.get("query_strategy"),
            )
        )

    op.drop_column("hosts", "ech")
