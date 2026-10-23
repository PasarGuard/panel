"""Deliver panel events to plugin handlers.

Hook point: ``app.notification._safe_notification_task``. Every facade call in ``app.notification`` goes
through that wrapper, which first claims a dedup slot (``claim_notification_slot``: in-process when
``UVICORN_WORKERS=1``, shared NATS KV otherwise). Plugin events are emitted right after a successful claim and
before the telegram/discord/webhook toggles are checked, so:

* each event reaches plugins once per cluster, in the process that observed it (API worker, node role,
  scheduler); the same 15 s dedup window that protects notifications applies (two identical events for the
  same object inside that window in a multi-worker setup are collapsed into one);
* plugin events fire even when every notification channel is disabled.

Handlers run as background tasks with a timeout; they never block or fail the original action.
"""

from __future__ import annotations

import asyncio
import inspect
from copy import deepcopy
from typing import Any

from pydantic import BaseModel

from app.plugins import registry
from app.utils.logger import get_logger

logger = get_logger("plugins")

HANDLER_TIMEOUT = 10.0
ALL_EVENTS = "*"
# Never handed to plugins: dropped from the payload top level and from the top level of each dumped model.
SENSITIVE_KEYS = frozenset({"password", "hashed_password", "api_key"})

# app.notification facade function -> plugin event name
EVENT_NAMES: dict[str, str] = {
    "create_api_key": "api_key.created",
    "modify_api_key": "api_key.modified",
    "remove_api_key": "api_key.removed",
    "create_admin_role": "admin_role.created",
    "modify_admin_role": "admin_role.modified",
    "remove_admin_role": "admin_role.removed",
    "create_host": "host.created",
    "modify_host": "host.modified",
    "remove_host": "host.removed",
    "modify_hosts": "hosts.modified",
    "create_user_template": "user_template.created",
    "modify_user_template": "user_template.modified",
    "remove_user_template": "user_template.removed",
    "create_node": "node.created",
    "modify_node": "node.modified",
    "remove_node": "node.removed",
    "connect_node": "node.connected",
    "recovered_node": "node.recovered",
    "error_node": "node.error",
    "limited_node": "node.limited",
    "reset_node_usage": "node.usage_reset",
    "create_group": "group.created",
    "modify_group": "group.modified",
    "remove_group": "group.removed",
    "create_admin": "admin.created",
    "modify_admin": "admin.modified",
    "remove_admin": "admin.removed",
    "admin_usage_reset": "admin.usage_reset",
    "admin_usage_limit_reached": "admin.usage_limit_reached",
    "admin_login": "admin.login",
    "user_status_change": "user.status_changed",
    "create_user": "user.created",
    "modify_user": "user.modified",
    "remove_user": "user.removed",
    "reset_user_data_usage": "user.usage_reset",
    "user_data_reset_by_next": "user.data_reset_by_next",
    "user_subscription_revoked": "user.subscription_revoked",
    "create_core": "core.created",
    "modify_core": "core.modified",
    "remove_core": "core.removed",
}

_tasks: set[asyncio.Task] = set()


def _to_json(name: str, value: Any) -> Any:
    if isinstance(value, BaseModel):
        if name == "by" and hasattr(value, "username"):
            return value.username
        dumped = value.model_dump(mode="json")
        if isinstance(dumped, dict):
            for key in SENSITIVE_KEYS:
                dumped.pop(key, None)
        return dumped
    if hasattr(value, "value") and not isinstance(value, (str, int, float, bool)):
        return value.value
    return value


def build_payload(event: str, func, args: tuple, kwargs: dict) -> dict:
    bound = inspect.signature(func).bind(*args, **kwargs)
    payload: dict[str, Any] = {"event": event}
    for name, value in bound.arguments.items():
        if name in SENSITIVE_KEYS:
            continue
        payload[name] = _to_json(name, value)
    return payload


def handlers_for(event: str) -> list[tuple[Any, Any]]:
    result = []
    for ctx in registry.active:
        for handler in (*ctx.handlers.get(event, ()), *ctx.handlers.get(ALL_EVENTS, ())):
            result.append((ctx, handler))
    return result


def emit(event: str, payload: dict) -> None:
    """Schedule all handlers for ``event``; returns immediately."""
    handlers = handlers_for(event)
    if not handlers:
        return
    task = asyncio.create_task(_dispatch(event, payload, handlers))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def emit_notification(func_name: str, func, args: tuple, kwargs: dict) -> None:
    """Called by the notification wrapper after the dedup claim. Never raises."""
    try:
        event = EVENT_NAMES.get(func_name)
        if event is None or not handlers_for(event):
            return
        emit(event, build_payload(event, func, args, kwargs))
    except Exception:
        logger.exception(f"Could not emit plugin event for {func_name}")


async def _run_handler(ctx, handler, event: str, payload: dict) -> None:
    try:
        result = handler(deepcopy(payload))
        if inspect.isawaitable(result):
            await asyncio.wait_for(result, timeout=HANDLER_TIMEOUT)
    except asyncio.CancelledError:
        raise
    except TimeoutError:
        ctx.logger.warning(f"Handler {getattr(handler, '__name__', handler)!r} for {event} timed out")
    except Exception:
        ctx.logger.exception(f"Handler {getattr(handler, '__name__', handler)!r} for {event} failed")


async def _dispatch(event: str, payload: dict, handlers: list) -> None:
    await asyncio.gather(*(_run_handler(ctx, handler, event, payload) for ctx, handler in handlers))


async def drain() -> None:
    """Wait for in-flight handler tasks (tests, shutdown)."""
    while _tasks:
        await asyncio.gather(*list(_tasks), return_exceptions=True)
