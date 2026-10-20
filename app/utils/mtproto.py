from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.models.proxy import ProxyTable, generate_mtproto_secret


async def mtproto_secret_in_use(
    db: AsyncSession,
    secret: str,
    *,
    exclude_user_id: int | None = None,
) -> bool:
    # Write paths store lowercase hex, but a legacy or hand-edited row can hold uppercase.
    stored = func.lower(User.proxy_settings["mtproto"]["secret"].as_string())
    stmt = select(User.id).where(stored == secret.lower()).limit(1)
    if exclude_user_id is not None:
        stmt = stmt.where(User.id != exclude_user_id)
    return (await db.execute(stmt)).first() is not None


async def prepare_mtproto_secret(
    db: AsyncSession,
    proxy_settings: ProxyTable,
    *,
    current_secret: str | None = None,
    exclude_user_id: int | None = None,
) -> ProxyTable:
    """Give the user an MTProto secret on a write path (create, modify, template, bulk create, revoke).

    No secret in the request keeps ``current_secret`` (so a modify that omits or clears it does not
    rotate a forwarded Telegram link), else a fresh random one is generated. A supplied secret that
    differs from ``current_secret`` must not belong to another user.
    """
    secret = proxy_settings.mtproto.secret
    if secret is None:
        proxy_settings.mtproto.secret = current_secret or generate_mtproto_secret()
        return proxy_settings

    if secret != current_secret and await mtproto_secret_in_use(db, secret, exclude_user_id=exclude_user_id):
        raise ValueError("mtproto secret is already assigned to another user")
    return proxy_settings
