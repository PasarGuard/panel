from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import job_settings

# Bound delayed executions instead of replaying a backlog or allowing default
# 30-way overlap. Explicit per-job settings continue to take precedence.
scheduler = AsyncIOScheduler(
    job_defaults={"max_instances": 1, "coalesce": True, "misfire_grace_time": job_settings.misfire_grace_time},
    timezone="UTC",
)
