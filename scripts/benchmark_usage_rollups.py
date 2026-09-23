"""Measure SQLite usage-history storage before and after daily rollups.

Run from the repository root with `python scripts/benchmark_usage_rollups.py`.
The synthetic database is created in a temporary directory and removed on exit.
"""

import asyncio
import json
import logging
import os
import sqlite3
import sys
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import models  # noqa: F401 - register all mapped tables
from app.db.base import Base
from app.jobs import compact_usages

NOW = datetime(2026, 9, 23, tzinfo=UTC)
compact_usages.logger.setLevel(logging.WARNING)
USERS = 40
RECENT_DAYS = 7
SCENARIOS = (
    ("14 old days, hourly", 14, 60),
    ("28 old days, hourly", 28, 60),
    ("14 old days, 10-minute", 14, 10),
)


def _snapshot(path: Path) -> dict:
    with closing(sqlite3.connect(path)) as connection:
        # Deleting rows frees pages for reuse; VACUUM measures reclaimed disk.
        connection.execute("VACUUM")
        user_rows, user_bytes = connection.execute(
            "SELECT count(*), coalesce(sum(used_traffic), 0) FROM node_user_usages"
        ).fetchone()
        node_rows, uplink, downlink = connection.execute(
            "SELECT count(*), coalesce(sum(uplink), 0), coalesce(sum(downlink), 0) FROM node_usages"
        ).fetchone()
    return {
        "rows": user_rows + node_rows,
        "user_bytes": user_bytes,
        "uplink": uplink,
        "downlink": downlink,
        "file_bytes": os.path.getsize(path),
    }


def _seed(path: Path, old_days: int, interval_minutes: int) -> None:
    first_day = NOW - timedelta(days=old_days + RECENT_DAYS)
    slots = 24 * 60 // interval_minutes
    with closing(sqlite3.connect(path)) as connection:
        user_batch = []
        node_batch = []
        for day in range(old_days + RECENT_DAYS):
            for slot in range(slots):
                instant = first_day + timedelta(days=day, minutes=slot * interval_minutes)
                stamp = instant.replace(tzinfo=None).isoformat(sep=" ")
                for user_id in range(1, USERS + 1):
                    user_batch.append((stamp, user_id, 1, user_id + slot + 1, 0))
                node_batch.append((stamp, 1, 100 + slot, 200 + slot, 0))
                if len(user_batch) >= 4000:
                    connection.executemany(
                        "INSERT INTO node_user_usages (created_at, user_id, node_id, used_traffic, is_daily) "
                        "VALUES (?, ?, ?, ?, ?)",
                        user_batch,
                    )
                    user_batch.clear()
                if len(node_batch) >= 4000:
                    connection.executemany(
                        "INSERT INTO node_usages (created_at, node_id, uplink, downlink, is_daily) "
                        "VALUES (?, ?, ?, ?, ?)",
                        node_batch,
                    )
                    node_batch.clear()
        if user_batch:
            connection.executemany(
                "INSERT INTO node_user_usages (created_at, user_id, node_id, used_traffic, is_daily) "
                "VALUES (?, ?, ?, ?, ?)",
                user_batch,
            )
        if node_batch:
            connection.executemany(
                "INSERT INTO node_usages (created_at, node_id, uplink, downlink, is_daily) VALUES (?, ?, ?, ?, ?)",
                node_batch,
            )
        connection.commit()


async def _run_scenario(name: str, old_days: int, interval_minutes: int) -> dict:
    with TemporaryDirectory(prefix="pasarguard-rollup-benchmark-") as temp_dir:
        path = Path(temp_dir) / "usage.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{path.as_posix()}")
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            _seed(path, old_days, interval_minutes)
            before = _snapshot(path)
            factory = async_sessionmaker(engine, expire_on_commit=False)

            class BenchmarkGetDB:
                async def __aenter__(self):
                    self.session = factory()
                    return self.session

                async def __aexit__(self, exc_type, exc, tb):
                    if exc_type is not None:
                        await self.session.rollback()
                    await self.session.close()

            original_get_db = compact_usages.GetDB
            compact_usages.GetDB = BenchmarkGetDB
            try:
                await compact_usages.compact_old_usages(NOW, max_days=old_days)
            finally:
                compact_usages.GetDB = original_get_db

            after = _snapshot(path)
            for key in ("user_bytes", "uplink", "downlink"):
                assert before[key] == after[key], f"{key} changed in {name}"
            return {
                "scenario": name,
                "users": USERS,
                "before_rows": before["rows"],
                "after_rows": after["rows"],
                "row_reduction_percent": round(100 * (1 - after["rows"] / before["rows"]), 1),
                "before_file_bytes": before["file_bytes"],
                "after_file_bytes": after["file_bytes"],
                "file_reduction_percent": round(100 * (1 - after["file_bytes"] / before["file_bytes"]), 1),
            }
        finally:
            await engine.dispose()


async def main() -> None:
    for scenario in SCENARIOS:
        print(json.dumps(await _run_scenario(*scenario)), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
