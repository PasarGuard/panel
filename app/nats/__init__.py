from config import nats_settings, runtime_settings, server_settings


def is_nats_enabled() -> bool:
    return nats_settings.enabled


def get_nats_config():
    return {
        "url": nats_settings.url,
    }


def is_multi_worker() -> bool:
    """True when process-local state must be shared across processes (needs NATS)."""
    return runtime_settings.role.requires_nats or server_settings.workers > 1


def needs_shared_bridge_memory() -> bool:
    """NATS KV user-sync/lifecycle only when multiple uvicorn workers share NodeManager."""
    return is_nats_enabled() and server_settings.workers > 1


def require_nats_if_multiworker(multi_worker: bool):
    if multi_worker and not is_nats_enabled():
        raise RuntimeError(
            "NATS is required for multi-worker / split-role deployments. "
            "Set NATS_ENABLED=1 and provide proper NATS configuration."
        )


__all__ = [
    "get_nats_config",
    "is_multi_worker",
    "is_nats_enabled",
    "needs_shared_bridge_memory",
    "require_nats_if_multiworker",
]
