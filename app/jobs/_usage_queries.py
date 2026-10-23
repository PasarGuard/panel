"""Dialect-specific history statements; callers own the transaction."""

from collections import defaultdict
from datetime import datetime as dt, timedelta as td

from sqlalchemy import BigInteger, DateTime, bindparam, case, func, or_, select, union_all, update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.postgresql import ARRAY, insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.models import Node, NodeUsage, NodeUserUsage, User

ONLINE_AT_WRITE_INTERVAL = td(minutes=1)
NODE_USER_USAGE_BATCH_SIZE_BY_DIALECT = {"mysql": 1000, "sqlite": 400}


def _chunked(items: list, size: int):
    for index in range(0, len(items), size):
        yield items[index : index + size]


def build_user_traffic_update(dialect: str, usage_params: list[dict]):
    """Build a set-based user traffic update on PostgreSQL and MySQL, an executemany one on SQLite."""
    if dialect in ("postgresql", "mysql"):
        aggregated_usage = defaultdict(int)
        for param in usage_params:
            aggregated_usage[param["uid"]] += param["value"]

        aggregated_usage = dict(sorted(aggregated_usage.items()))

    if dialect == "mysql":
        # asyncmy runs an executemany UPDATE as one round trip per row, so add the
        # deltas of the whole batch in one statement with a CASE on the primary key
        stmt = (
            update(User)
            .where(User.id.in_(list(aggregated_usage)))
            .values(used_traffic=User.used_traffic + case(aggregated_usage, value=User.id))
            .execution_options(synchronize_session=False)
        )
        return stmt, None

    if dialect == "postgresql":
        source = (
            func.unnest(
                bindparam("uids", type_=ARRAY(BigInteger())),
                bindparam("traffic_values", type_=ARRAY(BigInteger())),
            )
            .table_valued("uid", "value")
            .render_derived(name="usage_source")
        )
        stmt = (
            update(User)
            .where(User.id == source.c.uid)
            .values(used_traffic=User.used_traffic + source.c.value)
            .execution_options(synchronize_session=False)
        )
        return (
            stmt,
            {
                "uids": list(aggregated_usage),
                "traffic_values": list(aggregated_usage.values()),
            },
        )

    stmt = (
        update(User)
        .where(User.id == bindparam("uid"))
        .values(used_traffic=User.used_traffic + bindparam("value"))
        .execution_options(synchronize_session=False)
    )
    return stmt, usage_params


def build_online_at_updates(dialect: str, user_ids: list[int], now: dt):
    """Build throttled online timestamp updates without per-user statements."""
    if not user_ids:
        return []

    cutoff = now - ONLINE_AT_WRITE_INTERVAL
    stale_online_at = or_(User.online_at.is_(None), User.online_at <= cutoff)

    if dialect == "postgresql":
        source = (
            func.unnest(bindparam("online_user_ids", type_=ARRAY(BigInteger())))
            .table_valued("uid")
            .render_derived(name="online_users")
        )
        stmt = (
            update(User)
            .where(User.id == source.c.uid, stale_online_at)
            .values(online_at=now)
            .execution_options(synchronize_session=False)
        )
        return [(stmt, {"online_user_ids": user_ids})]

    batch_size = NODE_USER_USAGE_BATCH_SIZE_BY_DIALECT.get(dialect, len(user_ids))
    return [
        (
            update(User)
            .where(User.id.in_(batch), stale_online_at)
            .values(online_at=now)
            .execution_options(synchronize_session=False),
            None,
        )
        for batch in _chunked(user_ids, batch_size)
    ]


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
            .select_from(source.join(User, User.id == source.c.uid).join(Node, Node.id == source.c.node_id))
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

    if dialect == "mysql":
        # One statement that asyncmy sends as a multi-row VALUES list; building a UNION of
        # one SELECT per row cost more CPU than the write itself. IGNORE turns the foreign key
        # error of a user or node deleted since the stats were read into a warning and skips
        # that row, as the users and nodes join does on the other dialects.
        stmt = (
            mysql_insert(NodeUserUsage)
            .values(
                created_at=bindparam("created_at"),
                user_id=bindparam("uid"),
                node_id=bindparam("node_id"),
                used_traffic=bindparam("value"),
            )
            .prefix_with("IGNORE")
        )
        stmt = stmt.on_duplicate_key_update(used_traffic=NodeUserUsage.used_traffic + stmt.inserted.used_traffic)
        return [(stmt, upsert_params)]

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
        .select_from(source.join(User, User.id == source.c.uid).join(Node, Node.id == source.c.node_id))
        .group_by(source.c.created_at, source.c.uid, source.c.node_id)
    )

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
