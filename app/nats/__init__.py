from config import NATS_ENABLED, NATS_URL


def is_nats_enabled() -> bool:
    return NATS_ENABLED


def get_nats_config():
    return {
        "url": NATS_URL,
    }


def require_nats_if_multiworker(multi_worker: bool):
    if multi_worker and not is_nats_enabled():
        raise RuntimeError(
            "NATS is required when running more than 1 worker. "
            "Set NATS_ENABLED=1 and provide proper NATS configuration."
        )


__all__ = ["is_nats_enabled", "get_nats_config", "require_nats_if_multiworker"]
