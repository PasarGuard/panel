from sqlalchemy import select

from app.core.manager import core_manager
from app.db import AsyncSession
from app.db.crud.host import upsert_inbounds
from app.db.crud.inbound_ratio import (
    get_inbound_ratio_core_names,
    get_inbound_ratio_group_names,
    get_inbound_ratio_host_counts,
    get_inbound_ratio_map,
    save_inbound_ratio,
)
from app.db.models import ProxyInbound
from app.models.inbound_ratio import InboundRatioResponse
from app.operation import BaseOperation

InboundRatioSnapshot = tuple[
    dict[str, dict],
    dict[str, float],
    dict[str, list[str]],
    dict[str, int],
    dict[str, list[str]],
]


class InboundRatioOperation(BaseOperation):
    """Inbound usage-ratio settings. Inbound proxies themselves stay in the core config."""

    @staticmethod
    def _build_inbound_ratio_response(
        tag: str,
        live: dict[str, dict],
        ratios: dict[str, float],
        group_names: dict[str, list[str]],
        host_counts: dict[str, int],
        core_names: dict[str, list[str]],
    ) -> InboundRatioResponse:
        data = live.get(tag) or {}
        return InboundRatioResponse(
            tag=tag,
            protocol=data.get("protocol"),
            network=data.get("network"),
            security=data.get("tls"),
            usage_coefficient=ratios.get(tag, 1.0),
            hosts_count=host_counts.get(tag, 0),
            groups=group_names.get(tag, []),
            cores=core_names.get(tag, []),
        )

    @staticmethod
    async def _inbound_ratio_cores_by_tag(db: AsyncSession) -> dict[str, list[str]]:
        """Map inbound tag to the names of the cores that define it (a tag can be shared)."""
        core_ids_by_tag = await core_manager.get_inbound_ratio_core_ids()
        if not core_ids_by_tag:
            return {}
        names = await get_inbound_ratio_core_names(db)
        return {
            tag: [names[core_id] for core_id in core_ids if core_id in names]
            for tag, core_ids in core_ids_by_tag.items()
        }

    async def _load_snapshot(self, db: AsyncSession) -> InboundRatioSnapshot:
        """Load the live inbounds and every panel-side lookup used by the response builder."""
        live = await core_manager.get_inbounds_by_tag()
        ratios = await get_inbound_ratio_map(db)
        group_names = await get_inbound_ratio_group_names(db)
        host_counts = await get_inbound_ratio_host_counts(db)
        core_names = await self._inbound_ratio_cores_by_tag(db)
        return live, ratios, group_names, host_counts, core_names

    async def get_inbound_ratios(self, db: AsyncSession) -> list[InboundRatioResponse]:
        live, ratios, group_names, host_counts, core_names = await self._load_snapshot(db)
        # Live core inbounds plus rows the cleanup job has not removed yet, so a stored
        # ratio never disappears from the dashboard while its tag is still referenced.
        tags = sorted(set(live) | set(ratios))
        return [
            self._build_inbound_ratio_response(tag, live, ratios, group_names, host_counts, core_names) for tag in tags
        ]

    async def set_inbound_ratio(self, db: AsyncSession, tag: str, coefficient: float) -> InboundRatioResponse:
        inbound = await self._resolve_inbound_row(db, tag)
        await save_inbound_ratio(db, inbound, coefficient)

        live, ratios, group_names, host_counts, core_names = await self._load_snapshot(db)
        return self._build_inbound_ratio_response(tag, live, ratios, group_names, host_counts, core_names)

    async def _resolve_inbound_row(self, db: AsyncSession, tag: str) -> ProxyInbound:
        """Resolve an inbound by tag, creating the panel row when the live core config has it."""
        if await core_manager.get_inbound_by_tag(tag) is None:
            exists = (await db.execute(select(ProxyInbound.id).where(ProxyInbound.tag == tag))).first()
            if exists is None:
                await self.raise_error(f"Inbound {tag} not found", 404)
        return (await upsert_inbounds(db, [tag]))[tag]
