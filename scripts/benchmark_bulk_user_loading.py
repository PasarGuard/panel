"""Compare bulk CRUD before/after without touching the configured database.

Run from the repository root:
    python scripts/benchmark_bulk_user_loading.py --baseline 234ab68c --users 100 --logs 1000 --runs 5

Uses a separate in-memory SQLite database and fresh sessions for every sample.
Times the complete CRUD call (selection, update, commit and reload), excluding
fixture resets, response validation and node dispatch. Peak Python allocations
and SQL/ORM counts are collected in a separate, untimed run. SQLite timings are
not production PostgreSQL/MySQL or end-to-end API latency predictions.
"""

import argparse
import asyncio
import gc
import json
import statistics
import subprocess
import sys
import time
import tracemalloc
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, event, insert, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.db.crud import bulk
from app.db.models import Admin, AdminRole, Group, User, UserStatus, UserUsageResetLogs, users_groups_association
from app.models.group import BulkGroup
from app.models.proxy import ProxyTable
from app.models.user import BulkUser, BulkUsersProxy, UserResponse


def load_baseline(ref):
    """Load only a trusted revision from this local checkout for comparison."""
    source = subprocess.check_output(["git", "show", f"{ref}:app/db/crud/bulk.py"], encoding="utf-8")
    baseline = types.ModuleType("app.db.crud._benchmark_bulk_baseline")
    baseline.__package__ = "app.db.crud"
    exec(compile(source, f"{ref}:app/db/crud/bulk.py", "exec"), baseline.__dict__)  # noqa: S102
    return baseline


async def main(args, baseline):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    now = datetime.now(UTC).replace(microsecond=0)
    proxy = ProxyTable(shadowsocks={"password": "x" * 32, "method": "aes-128-gcm"}).model_dump(mode="json")
    async with factory() as db:
        role = AdminRole(name="benchmark-role")
        db.add(role)
        await db.flush()
        db.add(Admin(username="benchmark-admin", hashed_password="test", role_id=role.id))
        db.add(Group(name="benchmark-group", inbounds=[]))
        await db.flush()
        await db.execute(
            insert(User),
            [{"username": f"benchmark-{i}", "admin_id": 1, "created_at": now} for i in range(args.users)],
        )
        for uid in range(1, args.users + 1):
            if args.logs:
                await db.execute(
                    insert(UserUsageResetLogs),
                    [{"user_id": uid, "used_traffic_at_reset": n + 1} for n in range(args.logs)],
                )
        await db.commit()

    async def reset(action):
        async with factory() as db:
            await db.execute(
                update(User).values(
                    status=UserStatus.expired if action == "expire" else UserStatus.limited,
                    used_traffic=100,
                    data_limit=100,
                    expire=now - timedelta(days=1),
                    proxy_settings=proxy,
                )
            )
            await db.execute(delete(users_groups_association))
            if action != "add_groups":
                await db.execute(
                    insert(users_groups_association),
                    [{"user_id": uid, "groups_id": 1} for uid in range(1, args.users + 1)],
                )
            await db.commit()

    async def sample(module, action, name, model, *, profile=False):
        await reset(action)
        stats = {"sql_statements": 0, "history_objects": 0}

        def count_query(*unused):
            stats["sql_statements"] += 1

        def count_history(*unused):
            stats["history_objects"] += 1

        async with factory() as db:
            gc.collect()
            if profile:
                event.listen(engine.sync_engine, "before_cursor_execute", count_query)
                event.listen(UserUsageResetLogs, "load", count_history)
                tracemalloc.start()
            try:
                start = time.perf_counter()
                users, count = await getattr(module, name)(db, model)
                elapsed = (time.perf_counter() - start) * 1000
                if profile:
                    stats["peak_mib"] = tracemalloc.get_traced_memory()[1] / (1024 * 1024)
            finally:
                if profile:
                    tracemalloc.stop()
                    event.remove(engine.sync_engine, "before_cursor_execute", count_query)
                    event.remove(UserUsageResetLogs, "load", count_history)
            assert count == len(users) == args.users
            responses = [UserResponse.model_validate(user).model_dump(mode="json") for user in users]
            responses.sort(key=lambda user: user["id"])
            assert all(user["lifetime_used_traffic"] == 100 + args.logs * (args.logs + 1) // 2 for user in responses)
            return elapsed, stats, responses

    cases = [
        ("datalimit", "update_users_datalimit", BulkUser(amount=100)),
        ("expire", "update_users_expire", BulkUser(amount=2 * 86400)),
        ("add_groups", "add_groups_to_users", BulkGroup(group_ids={1})),
        ("remove_groups", "remove_groups_from_users", BulkGroup(group_ids={1})),
        ("proxy", "update_users_proxy_settings", BulkUsersProxy(method="xchacha20-poly1305")),
    ]
    print(
        json.dumps(
            {
                "python": sys.version,
                "baseline": args.baseline,
                "users": args.users,
                "logs_per_user": args.logs,
                "timing_samples": args.runs,
            }
        ),
        flush=True,
    )
    try:
        for action, name, model in cases:
            # Warm both SQL compilation caches before timing.
            before = await sample(baseline, action, name, model)
            after = await sample(bulk, action, name, model)
            assert before[2] == after[2], {
                key: (before[2][0][key], after[2][0][key])
                for key in before[2][0]
                if before[2][0][key] != after[2][0][key]
            }
            timings = {"before": [], "after": []}
            for run in range(args.runs):
                versions = [("before", baseline), ("after", bulk)]
                if run % 2:
                    versions.reverse()
                for label, module in versions:
                    elapsed, _, responses = await sample(module, action, name, model)
                    assert responses == before[2]
                    timings[label].append(elapsed)
            result = {"action": action, "responses_equal": True}
            for label, module in [("before", baseline), ("after", bulk)]:
                _, stats, responses = await sample(module, action, name, model, profile=True)
                assert responses == before[2]
                result[label] = {"median_ms": round(statistics.median(timings[label]), 3), **stats}
            print(json.dumps(result), flush=True)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default="234ab68c")
    parser.add_argument("--users", type=int, default=100)
    parser.add_argument("--logs", type=int, default=1000)
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()
    if args.users < 1 or args.logs < 0 or args.runs < 1:
        parser.error("users/runs must be positive and logs must be nonnegative")
    asyncio.run(main(args, load_baseline(args.baseline)))
