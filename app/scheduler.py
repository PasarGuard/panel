from apscheduler.schedulers.asyncio import AsyncIOScheduler


scheduler = AsyncIOScheduler(job_defaults={"max_instances": 1, "coalesce": True}, timezone="UTC")
