"""Compare the node-list query cost with a large reset-history table."""

from __future__ import annotations

import asyncio
import gc
import statistics
import time
import tracemalloc
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.crud.node import get_nodes
from app.db.models import Node, NodeUsageResetLogs
from app.models.node import NodeListQuery

PAGE_SIZE = 15
LOGS_PER_NODE = 1_000
TIMED_RUNS = 5


@dataclass(frozen=True)
class Measurement:
    median_ms: float
    peak_mib: float
    selects_per_run: float
    usage_log_objects_per_run: float
    identity_map_size: int


async def main() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with factory() as session:
        nodes = [
            Node(
                name=f"benchmark-node-{index:03d}",
                address=f"10.0.0.{index + 1}",
                port=62050,
                api_port=62051,
                server_ca="ca",
                api_key=f"key-{index}",
                core_config_id=None,
                uplink=index,
                downlink=index * 2,
            )
            for index in range(PAGE_SIZE)
        ]
        session.add_all(nodes)
        await session.flush()
        node_ids = [node.id for node in nodes]
        await session.execute(
            NodeUsageResetLogs.__table__.insert(),
            [
                {"node_id": node_id, "uplink": 1, "downlink": 2, "created_at": now}
                for node_id in node_ids
                for _ in range(LOGS_PER_NODE)
            ],
        )
        await session.commit()

    selects = 0
    loaded_logs = 0

    def count_selects(*args) -> None:
        nonlocal selects
        statement = args[2]
        if statement.lstrip().upper().startswith("SELECT"):
            selects += 1

    def count_loaded_logs(*args) -> None:
        nonlocal loaded_logs
        loaded_logs += 1

    event.listen(engine.sync_engine, "before_cursor_execute", count_selects)
    event.listen(NodeUsageResetLogs, "load", count_loaded_logs)

    async def query_page(*, load_usage_logs: bool, load_lifetime_usage: bool) -> int:
        async with factory() as session:
            nodes, total = await get_nodes(
                session,
                NodeListQuery(limit=PAGE_SIZE),
                load_usage_logs=load_usage_logs,
                load_lifetime_usage=load_lifetime_usage,
            )
            assert total == PAGE_SIZE
            lifetime_sum = sum(node.lifetime_used_traffic for node in nodes)
            assert lifetime_sum == PAGE_SIZE * LOGS_PER_NODE * 3 + sum(range(PAGE_SIZE)) * 3
            return len(session.identity_map)

    async def measure(*, load_usage_logs: bool, load_lifetime_usage: bool) -> Measurement:
        nonlocal selects, loaded_logs
        await query_page(load_usage_logs=load_usage_logs, load_lifetime_usage=load_lifetime_usage)
        selects = 0
        loaded_logs = 0

        durations = []
        identity_map_sizes = []
        for _ in range(TIMED_RUNS):
            gc.collect()
            started = time.perf_counter()
            identity_map_sizes.append(
                await query_page(load_usage_logs=load_usage_logs, load_lifetime_usage=load_lifetime_usage)
            )
            durations.append((time.perf_counter() - started) * 1_000)

        gc.collect()
        tracemalloc.start()
        identity_map_size = await query_page(
            load_usage_logs=load_usage_logs,
            load_lifetime_usage=load_lifetime_usage,
        )
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        assert len(set(identity_map_sizes + [identity_map_size])) == 1
        measured_runs = TIMED_RUNS + 1
        return Measurement(
            median_ms=statistics.median(durations),
            peak_mib=peak_bytes / 1024 / 1024,
            selects_per_run=selects / measured_runs,
            usage_log_objects_per_run=loaded_logs / measured_runs,
            identity_map_size=identity_map_size,
        )

    before = await measure(load_usage_logs=True, load_lifetime_usage=False)
    after = await measure(load_usage_logs=False, load_lifetime_usage=True)

    print(f"page_size={PAGE_SIZE} logs_per_node={LOGS_PER_NODE}")
    for label, measurement in (("before", before), ("after", after)):
        print(
            f"{label}: median_ms={measurement.median_ms:.2f} "
            f"peak_mib={measurement.peak_mib:.2f} "
            f"selects_per_run={measurement.selects_per_run:.1f} "
            f"usage_log_objects_per_run={measurement.usage_log_objects_per_run:.0f} "
            f"identity_map_size={measurement.identity_map_size}"
        )
    print(f"time_reduction_percent={(1 - after.median_ms / before.median_ms) * 100:.2f}")
    print(f"peak_memory_reduction_percent={(1 - after.peak_mib / before.peak_mib) * 100:.2f}")

    event.remove(NodeUsageResetLogs, "load", count_loaded_logs)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
