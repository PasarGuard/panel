from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.engine import make_url

from app.utils.logger import get_logger
from config import SCHEDULER_JOBSTORE_URL, SQLALCHEMY_DATABASE_URL

logger = get_logger("scheduler")


def _resolve_jobstore_url(jobstore_url: str) -> str:
    url = make_url(jobstore_url)
    driver_map = {
        "sqlite+aiosqlite": "sqlite",
        "postgresql+asyncpg": "postgresql+psycopg",
        "mysql+asyncmy": "mysql+pymysql",
    }

    if url.drivername in driver_map:
        url = url.set(drivername=driver_map[url.drivername])

    return str(url)


jobstore_url = SCHEDULER_JOBSTORE_URL or SQLALCHEMY_DATABASE_URL

try:
    jobstores = {"default": SQLAlchemyJobStore(url=_resolve_jobstore_url(jobstore_url))}
except ModuleNotFoundError as exc:
    missing_driver = getattr(exc, "name", "unknown driver")
    raise RuntimeError(
        f"Missing database driver ({missing_driver}) for APScheduler job store. "
        "Install a synchronous driver compatible with your configured SQLALCHEMY_DATABASE_URL."
    ) from exc

scheduler = AsyncIOScheduler(jobstores=jobstores, job_defaults={"max_instances": 30}, timezone="UTC")
