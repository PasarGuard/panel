"""Example plugin: an info line on top of links subscriptions and a {PLAN} format variable."""

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


def setup(ctx):
    # Subscriptions are rendered without loading the user's groups, so the plugin remembers
    # user id -> group names itself (refreshed on every render, see banner()).
    groups_by_user: dict[int, list[str]] = {}

    async def refresh_groups(user_id: int) -> None:
        query = (
            select(Group.name)
            .join(users_groups_association, users_groups_association.c.groups_id == Group.id)
            .where(users_groups_association.c.user_id == user_id)
        )
        async with ctx.db() as db:
            groups_by_user[user_id] = list((await db.execute(query)).scalars().all())

    def plan_for(user: dict) -> str:
        settings = ctx.settings.get()
        for name in groups_by_user.get(user["id"], []):
            if name in settings["plans"]:
                return str(settings["plans"][name])
        return settings["default_plan"]

    # Usable in host remarks and the profile title as {PLAN}. Variables are computed before transforms,
    # so a group change shows up in remarks from the next render on (the banner itself is always fresh).
    @ctx.subscription.variables
    def plan_variable(user: dict) -> dict:
        return {"PLAN": plan_for(user)}

    # Output depends only on the user and the settings, so it may be cached (default cache=True).
    @ctx.subscription.transform
    async def banner(user: dict, config_format: str, content):
        settings = ctx.settings.get()
        if not settings["enabled"] or config_format not in LINK_FORMATS or not isinstance(content, str):
            return None
        await refresh_groups(user["id"])
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
