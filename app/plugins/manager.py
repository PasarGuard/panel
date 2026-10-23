"""Wire loaded plugins into the app: routes, jobs, settings, NATS refresh.

Called from ``create_app`` only when ``PLUGINS`` is not empty.

Every process role loads the enabled plugins and runs ``setup()``, because events are emitted where
they happen (API in the panel, node health in the node role, user review jobs in the scheduler).
Routes are mounted only in roles that run the panel; jobs only in the scheduler role.
"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path

from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter, Depends, FastAPI
from fastapi.routing import APIRoute

from app.plugins import registry
from app.plugins.context import PluginContext, _public
from app.plugins.loader import load_plugin
from app.utils.logger import get_logger

logger = get_logger("plugins")

PLUGIN_API_PREFIX = "/api/plugins"
_pending: list[tuple[str, object]] = []


def load_all(plugins_dir: str | Path, plugin_ids: list[str], *, runs_panel: bool, runs_scheduler: bool):
    """Import enabled plugins and run sync setups. Returns contexts whose async setup is still pending."""
    plugins_dir = Path(plugins_dir)
    for plugin_id in plugin_ids:
        if plugin_id in registry.records:
            continue
        record, pending = load_plugin(plugins_dir, plugin_id, runs_panel=runs_panel, runs_scheduler=runs_scheduler)
        registry.records[plugin_id] = record
        if record.context is None:
            continue
        if pending is not None:
            _pending.append((plugin_id, pending))
        else:
            registry.active.append(record.context)
            logger.info(f"Plugin {plugin_id!r} {record.version} loaded")


def _is_public(route) -> bool:
    dependant = getattr(route, "dependant", None)
    stack = list(dependant.dependencies) if dependant is not None else []
    while stack:
        dependant = stack.pop()
        if dependant.call is _public:
            return True
        stack.extend(dependant.dependencies)
    return False


def _check_routes(routes, owner: str) -> None:
    """Allow only FastAPI HTTP routes: panel auth is applied as a router dependency, which Starlette routes,
    mounts and websockets do not run, so they would be public."""
    for route in routes:
        if isinstance(route, APIRoute):
            continue
        original = getattr(route, "original_router", None)
        if isinstance(original, APIRouter):
            _check_routes(list(original.routes) + list(getattr(original, "_low_priority_routes", [])), owner)
            continue
        path = getattr(route, "path", None) or type(route).__name__
        raise ValueError(
            f"Plugin route {path!r} of {owner!r} is not supported: only HTTP routes added with "
            "@ctx.router.get/post/put/patch/delete/api_route are allowed "
            "(websocket, mount and plain Starlette routes would bypass panel auth)"
        )


def split_routes(ctx: PluginContext) -> tuple[APIRouter, APIRouter]:
    """Split ``ctx.router`` into admin-only and public routes; raises on routes auth cannot protect."""
    protected = APIRouter()
    public = APIRouter()
    if not ctx.runs_panel:
        return protected, public
    _check_routes(ctx.router.routes, ctx.id)
    for route in ctx.router.routes:
        if isinstance(route, APIRoute) and _is_public(route):
            public.routes.append(route)
        else:
            protected.routes.append(route)
    return protected, public


def mount_routes(app: FastAPI, ctx: PluginContext, routers: tuple[APIRouter, APIRouter] | None = None) -> None:
    """Mount ``ctx.router`` at ``/api/plugins/<id>``; routes are admin-only unless marked public."""
    if not ctx.runs_panel or not ctx.router.routes:
        return
    protected, public = routers if routers is not None else split_routes(ctx)
    prefix = f"{PLUGIN_API_PREFIX}/{ctx.id}"
    tags = [f"Plugin: {ctx.id}"]
    if protected.routes:
        app.include_router(protected, prefix=prefix, tags=tags, dependencies=[Depends(ctx.deps.admin)])
    if public.routes:
        app.include_router(public, prefix=prefix, tags=tags)


def _job_wrapper(ctx: PluginContext, fn):
    async def run_plugin_job():
        try:
            result = fn()
            if inspect.isawaitable(result):
                await result
        except asyncio.CancelledError:
            raise
        except Exception:
            ctx.logger.exception(f"Plugin job {getattr(fn, '__name__', fn)!r} failed")

    run_plugin_job.__name__ = f"plugin_{ctx.id}_{getattr(fn, '__name__', 'job')}"
    return run_plugin_job


def _job_ids(ctx: PluginContext) -> list[str]:
    return [f"plugin:{ctx.id}:{getattr(fn, '__name__', 'job')}:{index}" for index, (fn, _) in enumerate(ctx.jobs)]


def register_jobs(ctx: PluginContext) -> None:
    """Add plugin jobs to the shared APScheduler (scheduler role only; paused while not the job leader)."""
    if not ctx.runs_scheduler:
        return
    from app.scheduler import scheduler

    for job_id, (fn, when) in zip(_job_ids(ctx), ctx.jobs):
        if "cron" in when:
            trigger = CronTrigger.from_crontab(when["cron"], timezone="UTC")
            scheduler.add_job(
                _job_wrapper(ctx, fn), trigger, id=job_id, replace_existing=True, max_instances=1, coalesce=True
            )
        else:
            scheduler.add_job(
                _job_wrapper(ctx, fn),
                "interval",
                seconds=when["seconds"],
                id=job_id,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )


def unregister_jobs(ctx: PluginContext) -> None:
    if not ctx.runs_scheduler:
        return
    from app.scheduler import scheduler

    for job_id in _job_ids(ctx):
        if scheduler.get_job(job_id) is not None:
            scheduler.remove_job(job_id)


def activate(app: FastAPI, ctx: PluginContext) -> None:
    """Check routes, add jobs, then mount routes; a failure leaves nothing of the plugin mounted or scheduled."""
    try:
        routers = split_routes(ctx)
        register_jobs(ctx)
        try:
            mount_routes(app, ctx, routers)
        except Exception:
            unregister_jobs(ctx)
            raise
    finally:
        ctx.activated = True


def activate_all(app: FastAPI) -> None:
    """Activate plugins whose sync setup succeeded; a plugin that fails activation is marked failed."""
    for ctx in list(registry.active):
        try:
            activate(app, ctx)
        except Exception as exc:
            registry.active.remove(ctx)
            record = registry.records[ctx.id]
            record.status = "failed"
            record.error = str(exc) or type(exc).__name__
            record.context = None
            logger.exception(f"Plugin {ctx.id!r} skipped: activation failed")


async def finish_pending_setups(app: FastAPI) -> None:
    """Await async ``setup()`` coroutines (startup), then mount what they registered."""
    while _pending:
        plugin_id, coro = _pending.pop(0)
        record = registry.records[plugin_id]
        try:
            await coro
        except Exception as exc:
            record.status = "failed"
            record.error = str(exc) or type(exc).__name__
            record.context = None
            logger.exception(f"Plugin {plugin_id!r} skipped: async setup failed")
            continue
        try:
            activate(app, record.context)
        except Exception as exc:
            record.status = "failed"
            record.error = str(exc) or type(exc).__name__
            record.context = None
            logger.exception(f"Plugin {plugin_id!r} skipped: activation failed")
            continue
        registry.active.append(record.context)
        logger.info(f"Plugin {plugin_id!r} {record.version} loaded")


def init_plugins(
    app: FastAPI, plugins_dir: str | Path, plugin_ids: list[str], *, runs_panel: bool, runs_scheduler: bool
):
    from app.lifecycle import on_startup
    from app.nats.message import MessageTopic
    from app.nats.router import router
    from app.plugins.settings import handle_plugin_message, load_settings_from_db

    load_all(plugins_dir, plugin_ids, runs_panel=runs_panel, runs_scheduler=runs_scheduler)
    activate_all(app)

    async def start_plugins(app: FastAPI):
        await load_settings_from_db(notify=False)
        await finish_pending_setups(app)

    on_startup(start_plugins)
    router.register_handler(MessageTopic.PLUGIN, handle_plugin_message)
