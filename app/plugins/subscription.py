"""Subscription hooks: content transforms, response headers, extra format variables.

Called from ``app.subscription.share`` and ``app.operation.subscription`` only when plugins are active.
A failing hook is logged and skipped; the subscription is still served.
"""

from __future__ import annotations

import base64
import inspect
import re
from typing import Any

from app.plugins import registry
from app.utils.logger import get_logger

logger = get_logger("plugins")

VARIABLE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def user_payload(user: Any) -> dict:
    if hasattr(user, "model_dump"):
        return user.model_dump(mode="json")
    return dict(user)


def _transforms(cached: bool):
    for ctx in registry.active:
        for fn, cache in ctx.subscription.transforms:
            if cache == cached:
                yield ctx, fn


def has_transforms(cached: bool) -> bool:
    return any(True for _ in _transforms(cached))


async def apply_transforms(user: Any, config_format: str, content: str | bytes, *, cached: bool) -> str | bytes:
    """Run transforms registered with ``cache=cached`` on decoded ``content``."""
    user_dict = None
    for ctx, fn in _transforms(cached):
        if user_dict is None:
            user_dict = user_payload(user)
        try:
            result = fn(user_dict, config_format, content)
            if inspect.isawaitable(result):
                result = await result
        except Exception:
            ctx.logger.exception(f"Subscription transform {getattr(fn, '__name__', fn)!r} failed")
            continue
        if result is None:
            continue
        if not isinstance(result, (str, bytes)):
            ctx.logger.warning(
                f"Subscription transform {getattr(fn, '__name__', fn)!r} returned {type(result).__name__}"
            )
            continue
        content = result
    return content


async def apply_uncached_transforms(
    user: Any, config_format: str, content: str | bytes, as_base64: bool
) -> str | bytes:
    """``cache=False`` transforms, applied to the (possibly cached) final body."""
    if not has_transforms(cached=False):
        return content
    if as_base64 and isinstance(content, str):
        try:
            decoded = base64.b64decode(content).decode()
        except ValueError, UnicodeDecodeError:
            return content
        result = await apply_transforms(user, config_format, decoded, cached=False)
        if isinstance(result, bytes):
            result = result.decode(errors="replace")
        return base64.b64encode(result.encode()).decode()
    return await apply_transforms(user, config_format, content, cached=False)


def apply_headers(user: Any, config_format: str | None, headers: dict) -> dict:
    user_dict = None
    for ctx in registry.active:
        for fn in ctx.subscription.header_hooks:
            if user_dict is None:
                user_dict = user_payload(user)
            try:
                result = fn(user_dict, config_format, dict(headers))
            except Exception:
                ctx.logger.exception(f"Subscription headers hook {getattr(fn, '__name__', fn)!r} failed")
                continue
            if isinstance(result, dict):
                headers.update({str(key): str(value) for key, value in result.items() if value is not None})
    return headers


def merge_variables(user: Any, format_variables: dict) -> dict:
    """Add plugin variables; keys already present (built-in variables) are never overridden."""
    user_dict = None
    for ctx in registry.active:
        for fn in ctx.subscription.variable_hooks:
            if user_dict is None:
                user_dict = user_payload(user)
            try:
                result = fn(user_dict)
            except Exception:
                ctx.logger.exception(f"Subscription variables hook {getattr(fn, '__name__', fn)!r} failed")
                continue
            if not isinstance(result, dict):
                continue
            for key, value in result.items():
                key = str(key)
                if not VARIABLE_KEY_RE.fullmatch(key) or key in format_variables:
                    continue
                format_variables[key] = "" if value is None else str(value)
    return format_variables
