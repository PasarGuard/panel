"""Dialect-specific history statements; callers own the transaction."""

from sqlalchemy import BigInteger, DateTime, bindparam, func, select, union_all
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.postgresql import ARRAY, insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.models import NodeUsage, NodeUserUsage, User


def build_node_user_usage_upsert(dialect: str, upsert_params: list[dict]):
    """
    Build UPSERT statement for NodeUserUsage based on database dialect.

    Args:
        dialect: Database dialect name ('postgresql', 'mysql', or 'sqlite')
        upsert_params: List of parameter dicts with keys: uid, node_id, created_at, value

    Returns:
        list: One SQL statement and its bound parameters.
    """
    if dialect == "postgresql":
        source = (
            func.unnest(
                bindparam("uids", type_=ARRAY(BigInteger())),
                bindparam("node_ids", type_=ARRAY(BigInteger())),
                bindparam("created_ats", type_=ARRAY(DateTime(timezone=True))),
                bindparam("traffic_values", type_=ARRAY(BigInteger())),
            )
            .table_valued("uid", "node_id", "created_at", "value")
            .render_derived(name="source")
        )

        select_stmt = (
            select(
                source.c.created_at,
                source.c.uid,
                source.c.node_id,
                func.sum(source.c.value).label("used_traffic"),
            )
            .select_from(source.join(User, User.id == source.c.uid))
            .group_by(source.c.created_at, source.c.uid, source.c.node_id)
        )

        stmt = pg_insert(NodeUserUsage).from_select(
            ["created_at", "user_id", "node_id", "used_traffic"],
            select_stmt,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["created_at", "user_id", "node_id"],
            set_={"used_traffic": NodeUserUsage.used_traffic + stmt.excluded.used_traffic},
        )
        return [
            (
                stmt,
                {
                    "uids": [param["uid"] for param in upsert_params],
                    "node_ids": [param["node_id"] for param in upsert_params],
                    "created_ats": [param["created_at"] for param in upsert_params],
                    "traffic_values": [param["value"] for param in upsert_params],
                },
            )
        ]

    select_parts = []
    stmt_params = {}
    for index, param in enumerate(upsert_params):
        uid_key = f"uid_{index}"
        node_id_key = f"node_id_{index}"
        created_at_key = f"created_at_{index}"
        value_key = f"value_{index}"
        select_parts.append(
            select(
                bindparam(uid_key).label("uid"),
                bindparam(node_id_key).label("node_id"),
                bindparam(created_at_key).label("created_at"),
                bindparam(value_key).label("value"),
            )
        )
        stmt_params[uid_key] = param["uid"]
        stmt_params[node_id_key] = param["node_id"]
        stmt_params[created_at_key] = param["created_at"]
        stmt_params[value_key] = param["value"]

    source = union_all(*select_parts).subquery("source")
    select_stmt = (
        select(
            source.c.created_at,
            source.c.uid,
            source.c.node_id,
            func.sum(source.c.value).label("used_traffic"),
        )
        .select_from(source.join(User, User.id == source.c.uid))
        .group_by(source.c.created_at, source.c.uid, source.c.node_id)
    )

    if dialect == "mysql":
        insert_source = select_stmt.subquery("insert_source")
        insert_select_stmt = select(
            insert_source.c.created_at,
            insert_source.c.uid,
            insert_source.c.node_id,
            insert_source.c.used_traffic,
        )
        stmt = mysql_insert(NodeUserUsage).from_select(
            ["created_at", "user_id", "node_id", "used_traffic"],
            insert_select_stmt,
        )
        stmt = stmt.on_duplicate_key_update(used_traffic=NodeUserUsage.used_traffic + insert_source.c.used_traffic)
        return [(stmt, stmt_params)]

    stmt = sqlite_insert(NodeUserUsage).from_select(
        ["created_at", "user_id", "node_id", "used_traffic"],
        select_stmt,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["created_at", "user_id", "node_id"],
        set_={"used_traffic": NodeUserUsage.used_traffic + stmt.excluded.used_traffic},
    )
    return [(stmt, stmt_params)]


def build_node_usage_upsert(dialect: str, upsert_param: dict):
    factory = {"postgresql": pg_insert, "mysql": mysql_insert, "sqlite": sqlite_insert}[dialect]
    stmt = factory(NodeUsage).values(
        node_id=bindparam("node_id"),
        created_at=bindparam("created_at"),
        uplink=bindparam("up"),
        downlink=bindparam("down"),
    )
    if dialect == "mysql":
        stmt = stmt.on_duplicate_key_update(
            uplink=NodeUsage.uplink + stmt.inserted.uplink,
            downlink=NodeUsage.downlink + stmt.inserted.downlink,
        )
    else:
        stmt = stmt.on_conflict_do_update(
            index_elements=["created_at", "node_id"],
            set_={
                "uplink": NodeUsage.uplink + stmt.excluded.uplink,
                "downlink": NodeUsage.downlink + stmt.excluded.downlink,
            },
        )
    return [(stmt, [upsert_param])]
