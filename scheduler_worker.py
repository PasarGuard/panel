import asyncio

import config as app_config  # noqa: E402

app_config.RUN_SCHEDULER = True

from app import app, lifespan  # noqa: E402
from app.core.redis_config import is_redis_enabled  # noqa: E402
from app.utils.logger import get_logger  # noqa: E402

logger = get_logger("scheduler-worker")


async def main():
    if not is_redis_enabled():
        logger.warning(
            "Redis is disabled; notification dispatching will only work when the scheduler shares a process with the API."
        )

    async with lifespan(app):
        try:
            while True:
                await asyncio.sleep(3600)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    asyncio.run(main())
