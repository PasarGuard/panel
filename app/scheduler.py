from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.engine import make_url

from app.utils.logger import get_logger
from config import SQLALCHEMY_DATABASE_URL

logger = get_logger("scheduler")


def _resolve_jobstore_url() -> str:
    url = make_url(SQLALCHEMY_DATABASE_URL)
    driver_map = {
        "sqlite+aiosqlite": "sqlite",
        "postgresql+asyncpg": "postgresql+psycopg",
        "mysql+asyncmy": "mysql+pymysql",
    }

    if url.drivername in driver_map:
        url = url.set(drivername=driver_map[url.drivername])

    return str(url)


try:
    jobstores = {"default": SQLAlchemyJobStore(url=_resolve_jobstore_url())}
except ModuleNotFoundError as exc:
    missing_driver = getattr(exc, "name", "unknown driver")
    raise RuntimeError(
        f"Missing database driver ({missing_driver}) for APScheduler job store. "
        "Install a synchronous driver compatible with your configured SQLALCHEMY_DATABASE_URL."
    ) from exc

scheduler = AsyncIOScheduler(jobstores=jobstores, job_defaults={"max_instances": 30}, timezone="UTC")
