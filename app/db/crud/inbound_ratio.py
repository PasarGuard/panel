from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CoreConfig, Group, ProxyHost, ProxyInbound, inbounds_groups_association as inbound_groups


async def get_inbound_ratio_map(db: AsyncSession) -> dict[str, float]:
    """Map every stored inbound tag to its usage ratio (missing rows default to 1.0)."""
    rows = (await db.execute(select(ProxyInbound.tag, ProxyInbound.usage_coefficient))).all()
    return {tag: 1.0 if coeff is None else float(coeff) for tag, coeff in rows}


async def get_inbound_ratio_group_names(db: AsyncSession) -> dict[str, list[str]]:
    """Map inbound tag to the names of the groups that expose it."""
    stmt = (
        select(ProxyInbound.tag, Group.name)
        .select_from(ProxyInbound)
        .join(inbound_groups, inbound_groups.c.inbound_id == ProxyInbound.id)
        .join(Group, Group.id == inbound_groups.c.group_id)
        .order_by(ProxyInbound.tag, Group.name)
    )
    grouped: dict[str, list[str]] = {}
    for tag, name in (await db.execute(stmt)).all():
        grouped.setdefault(tag, []).append(name)
    return grouped


async def get_inbound_ratio_core_names(db: AsyncSession) -> dict[int, str]:
    """Map core config id to its display name (plain column select, no JSON parsing)."""
    rows = (await db.execute(select(CoreConfig.id, CoreConfig.name))).all()
    return {core_id: name for core_id, name in rows}


async def get_inbound_ratio_host_counts(db: AsyncSession) -> dict[str, int]:
    """Map inbound tag to how many hosts reference it."""
    stmt = (
        select(ProxyInbound.tag, func.count(ProxyHost.id))
        .select_from(ProxyInbound)
        .outerjoin(ProxyHost, ProxyHost.inbound_tag == ProxyInbound.tag)
        .group_by(ProxyInbound.tag)
    )
    return {tag: int(count) for tag, count in (await db.execute(stmt)).all()}


async def save_inbound_ratio(db: AsyncSession, inbound: ProxyInbound, coefficient: float) -> ProxyInbound:
    """Persist the usage ratio of one inbound row."""
    inbound.usage_coefficient = float(coefficient)
    await db.commit()
    await db.refresh(inbound)
    return inbound
