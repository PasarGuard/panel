from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.crud.wireguard import _stored_wireguard_keys_in_use, get_wg_cores, tags_from_groups, wg_core_tags
from app.db.models import User
from app.models.proxy import ProxyTable
from app.utils.crypto import generate_wireguard_keypair, get_wireguard_public_key


async def wireguard_public_key_in_use(
    db: AsyncSession,
    public_key: str,
    *,
    exclude_user_id: int | None = None,
) -> bool:
    stmt = select(User.id).where(User.proxy_settings["wireguard"]["public_key"].as_string() == public_key).limit(1)
    if exclude_user_id is not None:
        stmt = stmt.where(User.id != exclude_user_id)
    return (await db.execute(stmt)).first() is not None


async def ensure_unique_wireguard_public_key(
    db: AsyncSession,
    proxy_settings: ProxyTable,
    *,
    exclude_user_id: int | None = None,
) -> None:
    public_key = proxy_settings.wireguard.public_key
    if not public_key:
        return
    if await wireguard_public_key_in_use(db, public_key, exclude_user_id=exclude_user_id):
        raise ValueError("wireguard public_key is already assigned to another user")


async def ensure_unique_wireguard_public_keys(db: AsyncSession, proxy_settings_list: Iterable[ProxyTable]) -> None:
    """ensure_unique_wireguard_public_key for a batch of new users, one lookup per 500 keys instead of one per user."""
    public_keys = [proxy_settings.wireguard.public_key for proxy_settings in proxy_settings_list]
    if await _stored_wireguard_keys_in_use(db, public_keys, excluded_user_ids=()):
        raise ValueError("wireguard public_key is already assigned to another user")


async def user_has_wireguard_access(db: AsyncSession, groups: Iterable) -> bool:
    wg_tags = wg_core_tags(await get_wg_cores(db))
    return bool(wg_tags and wg_tags & await tags_from_groups(groups))


async def prepare_wireguard_keys(
    db: AsyncSession,
    proxy_settings: ProxyTable,
    groups: Iterable,
    *,
    exclude_user_id: int | None = None,
    wireguard_access: bool | None = None,
) -> ProxyTable:
    """Ensure WG keys for a user assigned to a WireGuard interface.

    Peer IPs are managed by the subnet pool (app/db/crud/wireguard.py), never here.
    wireguard_access is user_has_wireguard_access(db, groups), when the caller already knows it.
    """
    if wireguard_access is None:
        wireguard_access = await user_has_wireguard_access(db, groups)
    if not wireguard_access:
        return proxy_settings

    await ensure_unique_wireguard_public_key(db, proxy_settings, exclude_user_id=exclude_user_id)

    if proxy_settings.wireguard.public_key and not proxy_settings.wireguard.private_key:
        raise ValueError("wireguard private_key is required when user is assigned to a WireGuard interface")

    if not proxy_settings.wireguard.private_key:
        private_key, public_key = generate_wireguard_keypair()
        proxy_settings.wireguard.private_key = private_key
        proxy_settings.wireguard.public_key = public_key
    elif not proxy_settings.wireguard.public_key:
        proxy_settings.wireguard.public_key = get_wireguard_public_key(proxy_settings.wireguard.private_key)

    return proxy_settings
