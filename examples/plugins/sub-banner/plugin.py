"""Example plugin: an info line on top of links subscriptions and a {PLAN} format variable."""

import asyncio
import time
from datetime import UTC, datetime
from urllib.parse import quote

from sqlalchemy import select

# Panel internals: allowed, but not a stable API.
from app.db.models import Group, users_groups_association

INFO_LINK = "vless://00000000-0000-0000-0000-000000000000@127.0.0.1:1?encryption=none&security=none&type=tcp#{remark}"
LINK_FORMATS = ("links", "links_base64")


def _days_left(user: dict) -> str:
    if not user.get("expire"):
        return "∞"
    expire = datetime.fromisoformat(user["expire"])
    if expire.tzinfo is None:
        expire = expire.replace(tzinfo=UTC)
    now = datetime.now(UTC)
    return str((expire - now).days + 1) if expire > now else "0"


def _data_left(user: dict) -> str:
    if not user.get("data_limit"):
        return "∞"
    left = max(user["data_limit"] - user.get("used_traffic", 0), 0)
    return f"{left / 1024**3:.2f} GB"


# user id -> group names. Subscriptions are rendered without the user's groups, and reading them in the
# hook would take a second database connection on every render while the request still holds its own.
# So hooks only read this map: it is loaded at startup, refreshed in the background every REFRESH_SECONDS,
# and updated at once from user events seen by this worker.
groups_by_user: dict[int, list[str]] = {}
REFRESH_SECONDS = 60


async def setup(ctx):
    groups_query = select(users_groups_association.c.user_id, Group.name).join(
        Group, users_groups_association.c.groups_id == Group.id
    )
    state = {"loaded_at": 0.0, "refresh": None}

    async def load_all() -> None:
        async with ctx.db() as db:
            rows = (await db.execute(groups_query)).all()
        fresh: dict[int, list[str]] = {}
        for user_id, name in rows:
            fresh.setdefault(user_id, []).append(name)
        groups_by_user.clear()
        groups_by_user.update(fresh)
        state["loaded_at"] = time.monotonic()

    async def refresh_in_background() -> None:
        try:
            await load_all()
        except Exception:
            ctx.logger.exception("Could not refresh user groups")
            state["loaded_at"] = time.monotonic()  # try again after REFRESH_SECONDS, not on every render
        finally:
            state["refresh"] = None

    def refresh_if_stale() -> None:
        if state["refresh"] is None and time.monotonic() - state["loaded_at"] > REFRESH_SECONDS:
            state["refresh"] = asyncio.create_task(refresh_in_background())

    # The event payload carries the user's group names; group changes made other ways (bulk actions, a group
    # renamed) and changes seen by other workers arrive with the next background refresh.
    async def user_changed(payload: dict) -> None:
        user = payload.get("user") or {}
        if "id" in user:
            groups_by_user[user["id"]] = list(user.get("group_names") or [])

    async def user_removed(payload: dict) -> None:
        groups_by_user.pop((payload.get("user") or {}).get("id"), None)

    ctx.on("user.created", user_changed)
    ctx.on("user.modified", user_changed)
    ctx.on("user.removed", user_removed)

    await load_all()

    def plan_for(user: dict) -> str:
        settings = ctx.settings.get()
        for name in groups_by_user.get(user["id"], []):
            if name in settings["plans"]:
                return str(settings["plans"][name])
        return settings["default_plan"]

    # Usable in host remarks and the profile title as {PLAN}.
    @ctx.subscription.variables
    def plan_variable(user: dict) -> dict:
        refresh_if_stale()
        return {"PLAN": plan_for(user)}

    # Output depends only on the user and the settings, so it may be cached (default cache=True).
    @ctx.subscription.transform
    def banner(user: dict, config_format: str, content):
        settings = ctx.settings.get()
        if not settings["enabled"] or config_format not in LINK_FORMATS or not isinstance(content, str):
            return None
        values = {
            "DAYS_LEFT": _days_left(user),
            "DATA_LEFT": _data_left(user),
            "USERNAME": user["username"],
            "PLAN": plan_for(user),
        }
        try:
            remark = settings["text"].format_map(values)
        except KeyError, ValueError, IndexError:
            remark = settings["text"]
        line = INFO_LINK.format(remark=quote(remark, safe=""))
        return f"{line}\n{content}" if content else line
