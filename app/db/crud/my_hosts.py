from sqlalchemy import select

from app.db import AsyncSession
from app.db.models import Admin, ProxyHost, ProxyInbound, inbounds_groups_association


async def get_personal_hosts(db: AsyncSession, allowed_groups: list[int] | None) -> list[ProxyHost]:
    stmt = select(ProxyHost).order_by(ProxyHost.priority, ProxyHost.id)
    if allowed_groups is not None:
        allowed_inbounds = (
            select(ProxyInbound.tag)
            .join(inbounds_groups_association, ProxyInbound.id == inbounds_groups_association.c.inbound_id)
            .where(inbounds_groups_association.c.group_id.in_(allowed_groups))
        )
        stmt = stmt.where(ProxyHost.inbound_tag.in_(allowed_inbounds))
    return list((await db.scalars(stmt)).all())


async def get_preferences_admin(db: AsyncSession, admin_id: int, *, lock: bool = False) -> Admin | None:
    stmt = select(Admin).where(Admin.id == admin_id).execution_options(populate_existing=True)
    if lock:
        stmt = stmt.with_for_update()
    return await db.scalar(stmt)
