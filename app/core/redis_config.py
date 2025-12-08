from config import REDIS_DB, REDIS_ENABLED, REDIS_HOST, REDIS_PORT


def is_redis_enabled() -> bool:
    return REDIS_ENABLED


def get_redis_config():
    return {
        "endpoint": REDIS_HOST,
        "port": REDIS_PORT,
        "db": REDIS_DB,
    }


def require_redis_if_multiworker(workers: int):
    if workers > 1 and not is_redis_enabled():
        raise RuntimeError(
            "Redis is required when running more than 1 worker. "
            "Set REDIS_ENABLED=1 and provide proper Redis configuration."
        )
