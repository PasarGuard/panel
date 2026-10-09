import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select, update

from app.db import AsyncSession, GetDB
from app.db.crud.warp import (
    claim_warp_apply,
    claim_warp_registration,
    finish_warp_registration,
    get_warp_settings,
    mark_warp_applied,
    release_warp_apply,
)
from app.db.models import CoreConfig, CoreType, Node, NodeStatus, NodeWarpProfile
from app.models.warp import CoreWarpResponse, WarpNodeResponse, WarpProfileStatus
from app.operation import BaseOperation, OperatorType
from app.utils.helpers import ensure_datetime_timezone
from app.utils.logger import get_logger
from app.utils.warp import WarpRegistrationError, register_warp

logger = get_logger("warp-operation")
_registration_semaphore = asyncio.Semaphore(3)
_tasks: dict[tuple[int, int | None], asyncio.Task] = {}


class WarpOperation(BaseOperation):
    @staticmethod
    async def ensure_profile(node_id: int, *, retry: bool = False) -> dict | None:
        # The semaphore is acquired before claiming the lease so queued work cannot outlive its lease.
        async with _registration_semaphore:
            async with GetDB() as db:
                settings = await get_warp_settings(db, node_id)
                if settings is not None:
                    return settings
                token = await claim_warp_registration(db, node_id, retry=retry)
            if token is None:
                return None
            try:
                settings = await register_warp()
            except WarpRegistrationError as exc:
                async with GetDB() as db:
                    await finish_warp_registration(db, node_id, token, error=str(exc))
                return None
            except asyncio.CancelledError:
                async with GetDB() as db:
                    await finish_warp_registration(db, node_id, token, error="Registration interrupted. Try again.")
                raise
            async with GetDB() as db:
                await finish_warp_registration(db, node_id, token, settings=settings)
                # A stale lease owner must not use credentials that were not persisted.
                return await get_warp_settings(db, node_id)

    @staticmethod
    async def node_config(node: Node, core) -> tuple[str, str | None]:
        original = core.to_str()
        if core.type != CoreType.xray or not getattr(core, "warp_outbound_tag", None):
            return original, None
        async with GetDB() as db:
            core_id = node.core_config_id or 1
            tag = await db.scalar(select(CoreConfig.warp_outbound_tag).where(CoreConfig.id == core_id))
        if not tag:
            return original, None
        config = json.loads(original)
        outbounds = config.get("outbounds", [])
        matches = [o for o in outbounds if o.get("tag") == tag]
        if len(matches) != 1 or matches[0].get("protocol") != "blackhole":
            raise ValueError("Managed WARP placeholder is missing; reload the core configuration")
        settings = await WarpOperation.ensure_profile(node.id)
        if settings is None:
            # Fail closed for traffic explicitly routed to WARP, keeping every other outbound intact.
            return original, None
        replacement = {
            "tag": tag,
            "protocol": "wireguard",
            "settings": deepcopy(settings),
            "targetStrategy": "ForceIPv4",
            "streamSettings": {"sockopt": {"domainStrategy": "ForceIPv4"}},
        }
        config["outbounds"] = [replacement if o.get("tag") == tag else o for o in outbounds]
        return json.dumps(config), tag

    @staticmethod
    async def applied(node: Node, tag: str) -> None:
        async with GetDB() as db:
            await mark_warp_applied(db, node.id, node.core_config_id or 1, tag)

    async def status(self, db: AsyncSession, core_id: int) -> CoreWarpResponse:
        core = await self.get_validated_core_config(db, core_id)
        condition = Node.core_config_id == core_id
        if core_id == 1:
            condition = or_(condition, Node.core_config_id.is_(None))
        rows = (
            await db.execute(
                select(Node.id, Node.name, Node.status, NodeWarpProfile)
                .outerjoin(NodeWarpProfile, NodeWarpProfile.node_id == Node.id)
                .where(condition)
                .order_by(Node.id)
            )
        ).all()
        now = datetime.now(UTC)
        nodes = []
        for node_id, name, node_status, profile in rows:
            status = WarpProfileStatus.pending
            if profile:
                if profile.lease_expires_at and ensure_datetime_timezone(profile.lease_expires_at) > now:
                    status = WarpProfileStatus.registering
                elif profile.last_error:
                    status = WarpProfileStatus.error
                elif profile.settings:
                    status = WarpProfileStatus.ready
                    if profile.applied_core_id == core_id and profile.applied_tag == core.warp_outbound_tag:
                        status = WarpProfileStatus.applied
            nodes.append(
                WarpNodeResponse(
                    node_id=node_id,
                    name=name,
                    node_status=node_status,
                    status=status,
                    registered_at=profile.registered_at if profile else None,
                    applied_at=profile.applied_at if profile and status == WarpProfileStatus.applied else None,
                    last_error=profile.last_error if profile else None,
                )
            )
        return CoreWarpResponse(outbound_tag=core.warp_outbound_tag, nodes=nodes)

    async def retry(self, db: AsyncSession, core_id: int, node_id: int | None) -> CoreWarpResponse:
        response = await self.status(db, core_id)
        if not response.outbound_tag:
            await self.raise_error("Save a managed WARP outbound in this core first", 400)
        if node_id is not None and not any(n.node_id == node_id for n in response.nodes):
            await self.raise_error("Node does not belong to this core", 404)
        self.schedule(core_id, node_id)
        return response

    @staticmethod
    def schedule(core_id: int, node_id: int | None = None) -> None:
        key = (core_id, node_id)
        if key in _tasks and not _tasks[key].done():
            return

        async def run():
            try:
                await WarpOperation.reconcile(core_id, node_id, retry=True)
            except Exception:
                # Only IDs and the exception type are logged by the per-node worker; never provider payloads.
                logger.warning("WARP reconciliation could not complete for core %s", core_id)
            finally:
                _tasks.pop(key, None)

        _tasks[key] = asyncio.create_task(run())

    @staticmethod
    async def reconcile(core_id: int | None = None, node_id: int | None = None, *, retry: bool = False) -> None:
        async with GetDB() as db:
            stmt = (
                select(Node.id, CoreConfig.id)
                .join(CoreConfig, CoreConfig.id == func.coalesce(Node.core_config_id, 1))
                .where(CoreConfig.warp_outbound_tag.is_not(None), Node.status == NodeStatus.connected)
            )
            if core_id is not None:
                stmt = stmt.where(CoreConfig.id == core_id)
            if node_id is not None:
                stmt = stmt.where(Node.id == node_id)
            nodes = (await db.execute(stmt)).all()
        semaphore = asyncio.Semaphore(3)

        async def reconcile_one(nid: int, cid: int):
            async with semaphore:
                apply_token = None
                try:
                    async with GetDB() as db:
                        core = await db.get(CoreConfig, cid)
                        node = await db.get(Node, nid)
                        profile = await db.get(NodeWarpProfile, nid)
                        if not core or not node or not core.warp_outbound_tag or (node.core_config_id or 1) != cid:
                            return
                        if profile:
                            if profile.applied_core_id == cid and profile.applied_tag == core.warp_outbound_tag:
                                return
                            if (
                                not retry
                                and profile.last_attempt_at
                                and ensure_datetime_timezone(profile.last_attempt_at)
                                > (datetime.now(UTC) - timedelta(minutes=5))
                            ):
                                return
                    if await WarpOperation.ensure_profile(nid, retry=retry) is None:
                        return
                    # Use the existing node operation so split roles and lifecycle fencing stay intact.
                    from app.operation.node import NodeOperation

                    async with GetDB() as db:
                        node = await db.get(Node, nid)
                        core = await db.get(CoreConfig, cid)
                        if not node or not core or (node.core_config_id or 1) != cid or not core.warp_outbound_tag:
                            return
                        apply_token = await claim_warp_apply(db, nid, cid, core.warp_outbound_tag)
                        if apply_token is None:
                            return
                        await NodeOperation(OperatorType.SYSTEM).connect_single_node(db, nid, force_start=True)
                        await db.refresh(node)
                        if node.status == NodeStatus.error:
                            raise ValueError("Node could not start")
                except Exception as exc:
                    logger.warning("WARP apply failed for node %s (%s)", nid, type(exc).__name__)
                    async with GetDB() as db:
                        await db.execute(
                            update(NodeWarpProfile)
                            .where(NodeWarpProfile.node_id == nid)
                            .values(
                                last_error="Could not apply WARP. Check the node and try again.",
                                last_attempt_at=datetime.now(UTC),
                            )
                        )
                        await db.commit()
                finally:
                    if apply_token:
                        async with GetDB() as db:
                            await release_warp_apply(db, nid, apply_token)

        await asyncio.gather(*(reconcile_one(nid, cid) for nid, cid in nodes))


async def shutdown_warp_tasks() -> None:
    tasks = list(_tasks.values())
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
