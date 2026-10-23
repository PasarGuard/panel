"""The only public API a plugin gets: ``setup(ctx: PluginContext)``.

Anything else in the panel (``app.*``) may be imported by plugins at their own risk: it is internal
and can change in any release.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from copy import deepcopy
from typing import Any

from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter

from app.plugins import schema
from app.utils.logger import get_logger

EventHandler = Callable[[dict], Any]
TransformFn = Callable[[dict, str, str | bytes], Any]
HeadersFn = Callable[[dict, str | None, dict], dict | None]
VariablesFn = Callable[[dict], dict]


async def _public() -> None:
    """Marker dependency: the route does its own authentication."""
    return


class PluginDeps:
    """FastAPI dependencies for plugin routes.

    Routes on ``ctx.router`` require an authenticated admin unless they declare
    ``dependencies=[Depends(ctx.deps.public)]`` (then the plugin is responsible for auth).
    """

    public = staticmethod(_public)

    @property
    def admin(self):
        from app.routers.authentication import get_current

        return get_current

    @property
    def owner(self):
        from app.routers.authentication import require_owner

        return require_owner


class PluginSubscription:
    def __init__(self) -> None:
        self.transforms: list[tuple[TransformFn, bool]] = []
        self.header_hooks: list[HeadersFn] = []
        self.variable_hooks: list[VariablesFn] = []

    def transform(self, fn: TransformFn | None = None, *, cache: bool = True):
        """Register ``fn(user, config_format, content) -> str | bytes | None`` (None = unchanged).

        ``cache=True`` (default): applied while rendering, so the result is stored in the short subscription
        cache; output must depend only on the user and the format. ``cache=False``: applied on every request
        after the cache lookup. Usable as ``@ctx.subscription.transform`` or ``transform(fn, cache=False)``.
        """

        def register(func: TransformFn) -> TransformFn:
            self.transforms.append((func, cache))
            return func

        return register(fn) if fn is not None else register

    def headers(self, fn: HeadersFn) -> HeadersFn:
        """Register ``fn(user, config_format, headers) -> dict | None`` (sync); returned keys are merged."""
        self.header_hooks.append(fn)
        return fn

    def variables(self, fn: VariablesFn) -> VariablesFn:
        """Register ``fn(user) -> dict[str, str]`` (sync) with extra UPPERCASE format variables."""
        self.variable_hooks.append(fn)
        return fn


class PluginSettingsAccess:
    def __init__(self, plugin_id: str, settings_schema: dict | None, logger: logging.Logger) -> None:
        self._plugin_id = plugin_id
        self._schema = settings_schema
        self._logger = logger
        self._values: dict = self.defaults()
        self.change_hooks: list[Callable[[dict], Any]] = []

    @property
    def schema(self) -> dict | None:
        return self._schema

    def defaults(self) -> dict:
        values = schema.apply_defaults(self._schema, {})
        return values if isinstance(values, dict) else {}

    def get(self) -> dict:
        """Current settings, validated against the schema, defaults applied (a copy)."""
        return deepcopy(self._values)

    def on_change(self, fn: Callable[[dict], Any]) -> Callable[[dict], Any]:
        """Register ``fn(new_settings)`` (sync or async), called in every worker after settings change."""
        self.change_hooks.append(fn)
        return fn

    def resolve(self, data: Any) -> tuple[dict, list[str]]:
        """Apply defaults and validate raw stored/submitted data."""
        if data is None:
            data = {}
        if not isinstance(data, dict):
            return self.defaults(), ["$: expected object"]
        values = schema.apply_defaults(self._schema, data)
        return values, schema.validate(self._schema, values)

    def set_values(self, values: dict) -> None:
        self._values = deepcopy(values)


class PluginContext:
    def __init__(
        self,
        plugin_id: str,
        version: str,
        settings_schema: dict | None = None,
        *,
        runs_panel: bool = True,
        runs_scheduler: bool = True,
    ) -> None:
        self.id = plugin_id
        self.version = version
        self.logger = get_logger(f"plugin.{plugin_id}")
        self.router = APIRouter()
        self.deps = PluginDeps()
        self.subscription = PluginSubscription()
        self.settings = PluginSettingsAccess(plugin_id, settings_schema, self.logger)
        self.runs_panel = runs_panel
        self.runs_scheduler = runs_scheduler
        self.handlers: dict[str, list[EventHandler]] = {}
        self.jobs: list[tuple[Callable, dict]] = []
        self.activated = False

    def on(self, event: str, handler: EventHandler | None = None):
        """Register an async ``handler(payload)`` for ``event`` (e.g. ``"user.created"``) or ``"*"``."""

        def register(func: EventHandler) -> EventHandler:
            self.handlers.setdefault(event, []).append(func)
            return func

        return register(handler) if handler is not None else register

    def job(self, fn: Callable, *, seconds: float | None = None, cron: str | None = None) -> Callable:
        """Run ``fn()`` (sync or async) every ``seconds`` or on a crontab ``cron`` ("0 9 * * *", UTC).

        Scheduled only in the scheduler role and only while this process is the job leader.
        Must be called from ``setup()``.
        """
        if self.activated:
            raise RuntimeError("ctx.job() must be called from setup()")
        if (seconds is None) == (cron is None):
            raise ValueError("ctx.job() needs exactly one of seconds= or cron=")
        if seconds is not None and seconds <= 0:
            raise ValueError("ctx.job(seconds=...) must be positive")
        if cron is not None:
            try:
                CronTrigger.from_crontab(cron, timezone="UTC")
            except ValueError as exc:
                raise ValueError(f"ctx.job(cron={cron!r}) is not a valid crontab: {exc}") from None
        self.jobs.append((fn, {"seconds": seconds} if seconds is not None else {"cron": cron}))
        return fn

    def db(self):
        """Async context manager yielding a database session (``async with ctx.db() as db``). Full access."""
        from app.db import GetDB

        return GetDB()
