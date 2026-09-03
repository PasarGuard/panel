"""Compare admin block/unblock loading and node serialization against a trusted local git revision.

Uses its own in-memory SQLite database and captures dispatch; no configured database or node is contacted.
Run: python scripts/benchmark_admin_user_sync_loading.py --baseline 234ab68c --users 100 --logs 1000 --runs 5
"""

import argparse
import asyncio
import gc
import json
import statistics
import subprocess
import sys
import tracemalloc
from pathlib import Path
from time import perf_counter
from types import ModuleType
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import event, insert, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import joinedload

from app.db import Base
from app.db.models import Admin, AdminRole, AdminStatus, Group, ProxyInbound, User, UserUsageResetLogs
from app.nats.proto_utils import serialize_proto_messages
from app.node import sync as node_sync
from app.operation import admin_sync


def load_baseline(ref):
    """Execute only code from a revision the person running this script trusts."""
    module = ModuleType("baseline_admin_sync")
    source = subprocess.check_output(["git", "show", f"{ref}:app/operation/admin_sync.py"], text=True)
    exec(compile(source, f"{ref}:app/operation/admin_sync.py", "exec"), module.__dict__)  # noqa: S102
    # Pin the loader too, so later edits to get_users do not affect the baseline.
    crud = ModuleType("baseline_user_crud")
    crud.__package__ = "app.db.crud"
    source = subprocess.check_output(["git", "show", f"{ref}:app/db/crud/user.py"], text=True)
    exec(compile(source, f"{ref}:app/db/crud/user.py", "exec"), crud.__dict__)  # noqa: S102
    module.get_users = crud.get_users
    return module


async def seed(factory, user_count, logs):
    async with factory() as db:
        role = AdminRole(name="benchmark-role")
        db.add(role)
        await db.flush()
        admin = Admin(username="benchmark", hashed_password="test", role_id=role.id)
        group = Group(name="benchmark", inbounds=[ProxyInbound(tag="benchmark")])
        db.add_all([admin, group])
        await db.flush()
        for i in range(user_count):
            user = User(username=f"user-{i}", admin_id=admin.id, proxy_settings={"trojan": {"password": f"test-{i}"}})
            user.groups = [group]
            db.add(user)
        await db.flush()
        # Bounded insertion batches keep fixture creation independent of the measured loads.
        for uid in range(1, user_count + 1):
            for start in range(0, logs, 1000):
                await db.execute(
                    insert(UserUsageResetLogs),
                    [{"user_id": uid, "used_traffic_at_reset": 100} for _ in range(min(1000, logs - start))],
                )
        await db.commit()


async def sample(factory, module, unblock, *, profile=False):
    async with factory() as db:
        admin = (await db.scalars(select(Admin).where(Admin.id == 1).options(joinedload(Admin.role)))).one()
        queue = asyncio.Queue()

        async def capture(users):
            await queue.put(users)

        counters = {"sql": 0, "history_objects": 0}

        def on_sql(*args):
            counters["sql"] += 1

        def on_history(*args):
            counters["history_objects"] += 1

        gc.collect()
        if profile:
            event.listen(db.bind.sync_engine, "before_cursor_execute", on_sql)
            event.listen(UserUsageResetLogs, "load", on_history)
            tracemalloc.start()
        try:
            with patch.object(node_sync, "_dispatch_users_update", capture):
                start = perf_counter()
                count = await module.sync_admin_users_for_block_transition(db, admin, was_blocked=unblock)
                proto_users = await queue.get()
                elapsed = (perf_counter() - start) * 1000
            if profile:
                counters["peak_mib"] = tracemalloc.get_traced_memory()[1] / 1024**2
        finally:
            if profile:
                tracemalloc.stop()
                event.remove(db.bind.sync_engine, "before_cursor_execute", on_sql)
                event.remove(UserUsageResetLogs, "load", on_history)
        # Compare complete messages outside timing; inbound order has no semantic meaning.
        messages = serialize_proto_messages(proto_users)
        for message in messages:
            message["inbounds"] = sorted(message.get("inbounds", []))
        messages.sort(key=lambda message: int(message["email"]))
        assert count == len(messages)
        return elapsed, counters, messages


async def main(args, baseline):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await seed(factory, args.users, args.logs)
        for unblock in (False, True):
            async with factory() as db:
                await db.execute(update(Admin).values(status=AdminStatus.active if unblock else AdminStatus.limited))
                await db.commit()
            versions = {"before": baseline, "after": admin_sync}
            expected = None
            timings = {name: [] for name in versions}
            for run in range(args.runs + 1):
                for name in list(versions) if run % 2 == 0 else list(reversed(versions)):
                    elapsed, _, messages = await sample(factory, versions[name], unblock)
                    if expected is None:
                        expected = messages
                    assert messages == expected
                    assert len(messages) == args.users
                    assert all(message["inbounds"] == (["benchmark"] if unblock else []) for message in messages)
                    if run:  # One warmup per version.
                        timings[name].append(elapsed)
            result = {
                "operation": "unblock" if unblock else "block",
                "users": args.users,
                "logs_per_user": args.logs,
                "runs": args.runs,
            }
            for name, module in versions.items():
                _, counters, messages = await sample(factory, module, unblock, profile=True)
                assert messages == expected
                result[name] = {"median_ms": round(statistics.median(timings[name]), 3), **counters}
            print(json.dumps(result), flush=True)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, help="Trusted local git revision to execute")
    parser.add_argument("--users", type=int, default=100)
    parser.add_argument("--logs", type=int, default=1000)
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()
    if args.users < 1 or args.logs < 0 or args.runs < 1:
        parser.error("users/runs must be positive and logs must be nonnegative")
    asyncio.run(main(args, load_baseline(args.baseline)))
