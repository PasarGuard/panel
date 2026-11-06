import asyncio

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.scheduler import scheduler


@pytest.mark.asyncio
async def test_a_job_without_its_own_max_instances_never_overlaps_itself():
    probe = AsyncIOScheduler(job_defaults=dict(scheduler._job_defaults), timezone="UTC")
    running = 0
    peak = 0

    async def slow_job():
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        try:
            await asyncio.sleep(0.5)
        finally:
            running -= 1

    probe.add_job(slow_job, "interval", seconds=0.1, id="slow_job")
    probe.start()
    try:
        await asyncio.sleep(1.2)
    finally:
        probe.shutdown(wait=False)

    assert peak == 1, f"{peak} runs of the same job were in flight at once"
