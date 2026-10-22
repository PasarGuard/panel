"""
The usage chart and user count queries pick a cheaper shape per dialect (no users join without an admin scope,
DISTINCT (bucket, user) pairs on PostgreSQL). These tests run every shape on the same generated history and
expect identical results, on whichever database the suite runs against.
"""

import asyncio
from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, event

from app.db.crud import user as user_crud
from app.db.models import Admin, Node, NodeUserUsage, User, UserStatus
from app.models.proxy import ProxyTable
from app.models.stats import Period, UserCountMetric
from tests.api import IS_SQLITE, TestSession, engine

# A window of its own, far from the rows other tests write
BASE = datetime(2031, 3, 1, tzinfo=UTC)
TIMEZONES = [UTC, timezone(timedelta(hours=3, minutes=30)), timezone(timedelta(hours=-5))]


@pytest.fixture(scope="module")
def usage_history():
    history = asyncio.run(_create_usage_history())
    yield history
    asyncio.run(_delete_usage_history(history))


async def _create_usage_history() -> dict:
    suffix = uuid4().hex[:8]
    async with TestSession() as session:
        admins = [Admin(username=f"shape_admin{i}_{suffix}", hashed_password="secret", role_id=3) for i in range(2)]
        session.add_all(admins)
        await session.flush()

        statuses = [UserStatus.active, UserStatus.expired, UserStatus.limited, UserStatus.active, UserStatus.expired]
        users = [
            User(
                username=f"shape_user{i}_{suffix}",
                admin_id=None if i == 4 else admins[i % 2].id,
                status=status,
                proxy_settings=ProxyTable().dict(no_obj=True),
            )
            for i, status in enumerate(statuses)
        ]
        session.add_all(users)
        nodes = [
            Node(
                name=f"shape_node{i}_{suffix}",
                address="127.0.0.1",
                port=8080,
                api_port=62051,
                server_ca="ca",
                api_key="key",
                core_config_id=None,
            )
            for i in range(2)
        ]
        session.add_all(nodes)
        await session.flush()

        # Bucket edges: UTC midnight, local midnight at +03:30 and -05:00, the last minute of a day, a month edge
        moments = [
            BASE,
            BASE - timedelta(hours=3, minutes=30),
            BASE + timedelta(hours=5),
            BASE + timedelta(hours=23, minutes=50),
            BASE + timedelta(days=1, hours=1),
            BASE + timedelta(days=3, minutes=10),
            BASE - timedelta(minutes=10),
            BASE + timedelta(days=31),
        ]
        rows = []
        for moment_index, moment in enumerate(moments):
            for user_index, user in enumerate(users):
                if (moment_index + user_index) % 3 == 2:
                    continue
                for node_index, node in enumerate(nodes):
                    if (moment_index * user_index + node_index) % 2:
                        rows.append(
                            NodeUserUsage(
                                created_at=moment,
                                user_id=user.id,
                                node_id=node.id,
                                used_traffic=1000 * (moment_index + 1) + 10 * user_index + node_index,
                            )
                        )
            # A row without a node, as the node usage path allows
            rows.append(
                NodeUserUsage(created_at=moment, user_id=users[moment_index % 5].id, node_id=None, used_traffic=7)
            )
        session.add_all(rows)
        await session.commit()
        return {
            "admins": [admin.username for admin in admins],
            "admin_ids": [admin.id for admin in admins],
            "user_ids": [user.id for user in users],
            "nodes": [node.id for node in nodes],
        }


async def _delete_usage_history(history: dict) -> None:
    async with TestSession() as session:
        await session.execute(delete(NodeUserUsage).where(NodeUserUsage.user_id.in_(history["user_ids"])))
        await session.execute(delete(User).where(User.id.in_(history["user_ids"])))
        await session.execute(delete(Node).where(Node.id.in_(history["nodes"])))
        await session.execute(delete(Admin).where(Admin.id.in_(history["admin_ids"])))
        await session.commit()


def _ranges(tz):
    start = BASE.astimezone(tz) - timedelta(days=1)
    return [
        (start, start + timedelta(days=40)),
        (start + timedelta(hours=1), start + timedelta(days=2, hours=1)),
        (datetime(2032, 1, 1, tzinfo=tz), datetime(2032, 1, 2, tzinfo=tz)),  # empty range
    ]


def _usage_scopes(history):
    admins = history["admins"]
    node_one = history["nodes"][0]
    return [
        {},
        {"group_by_node": True},
        {"group_by_admin": True},
        {"node_id": node_one},
        {"admins": [admins[0]]},
        {"admins": admins, "group_by_node": True},
        {"admins": [admins[1]], "group_by_admin": True},
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("tz", TIMEZONES, ids=["utc", "plus0330", "minus05"])
@pytest.mark.parametrize("period", [Period.hour, Period.day, Period.month])
async def test_all_users_usages_same_with_and_without_users_join(usage_history, monkeypatch, tz, period):
    seen_buckets = 0
    for start, end in _ranges(tz):
        for scope in _usage_scopes(usage_history):
            async with TestSession() as session:
                new = await user_crud.get_all_users_usages(
                    session, scope.get("admins"), start, end, period, **_without_admins(scope)
                )
            with monkeypatch.context() as patch:
                patch.setattr(user_crud, "_usage_history_needs_users_join", lambda *args: True)
                async with TestSession() as session:
                    joined = await user_crud.get_all_users_usages(
                        session, scope.get("admins"), start, end, period, **_without_admins(scope)
                    )
            assert new.model_dump() == joined.model_dump(), (scope, start, end)
            seen_buckets += sum(len(stats) for stats in new.stats.values())
    assert seen_buckets > 0


@pytest.mark.asyncio
@pytest.mark.parametrize("tz", TIMEZONES, ids=["utc", "plus0330", "minus05"])
@pytest.mark.parametrize("period", [Period.hour, Period.day, Period.month])
async def test_user_count_buckets_same_for_both_query_shapes(usage_history, monkeypatch, tz, period):
    admins = usage_history["admins"]
    node_one = usage_history["nodes"][0]
    scopes = [
        (UserCountMetric.online, {}),
        (UserCountMetric.online, {"group_by_node": True}),
        (UserCountMetric.online, {"node_id": node_one}),
        (UserCountMetric.online, {"admins": [admins[0]], "group_by_node": True}),
        (UserCountMetric.expired, {}),
        (UserCountMetric.expired, {"admins": admins}),
        (UserCountMetric.limited, {}),
        (UserCountMetric.limited, {"admins": [admins[1]]}),
    ]
    seen_counts = 0
    for start, end in _ranges(tz):
        for metric, scope in scopes:
            results = []
            for use_pairs in (False, True):
                with monkeypatch.context() as patch:
                    patch.setattr(
                        user_crud,
                        "_user_count_buckets_from_distinct_pairs",
                        lambda dialect, use_pairs=use_pairs: use_pairs,
                    )
                    async with TestSession() as session:
                        results.append(
                            await user_crud.get_user_count_metric_stats(
                                session, scope.get("admins"), start, end, period, metric, **_without_admins(scope)
                            )
                        )
            assert results[0].model_dump() == results[1].model_dump(), (metric, scope, start, end)
            seen_counts += sum(stat.count for stats in results[0].stats.values() for stat in stats)
    assert seen_counts > 0


def _without_admins(scope: dict) -> dict:
    return {key: value for key, value in scope.items() if key != "admins"}


@pytest.mark.asyncio
async def test_usage_chart_and_count_query_shapes_per_dialect(usage_history):
    statements: list[str] = []

    def _capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(" ".join(statement.split()).lower())

    start, end = _ranges(UTC)[0]
    event.listen(engine.sync_engine, "before_cursor_execute", _capture)
    try:
        async with TestSession() as session:
            await user_crud.get_all_users_usages(session, None, start, end, Period.day)
            usage_sql = statements[-1]
            await user_crud.get_user_count_metric_stats(session, None, start, end, Period.day, UserCountMetric.online)
            bucket_sql = statements[-1]
            dialect = session.bind.dialect.name
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _capture)

    # Orphan history rows only exist on SQLite, which does not enforce ON DELETE CASCADE
    assert ("join users" in usage_sql) == IS_SQLITE
    assert ("select distinct" in bucket_sql) == (dialect == "postgresql")
