import asyncio
import json
import uuid

import nats
from PasarGuardNodeBridge import NodeAPIError

from app import on_shutdown, on_startup
from app.db import GetDB
from app.db.crud.node import get_node_by_id, get_nodes
from app.db.crud.user import get_user, get_users
from app.db.models import UserStatus
from app.models.node import NodeCoreUpdate, NodeGeoFilesUpdate
from app.models.user import UserResponse
from app.nats import is_nats_enabled
from app.nats.client import create_nats_client
from app.node import node_manager
from app.operation import OperatorType
from app.operation.node import NodeOperation
from app.utils.logger import get_logger
from config import (
    IS_NODE_WORKER,
    NATS_NODE_COMMAND_SUBJECT,
    NATS_NODE_LOG_SUBJECT,
    NATS_NODE_RPC_SUBJECT,
)

logger = get_logger("node-worker")


class NodeWorkerService:
    def __init__(self):
        self._nc: nats.NATS | None = None
        self._command_sub: nats.aio.subscription.Subscription | None = None
        self._rpc_sub: nats.aio.subscription.Subscription | None = None
        self._log_tasks: dict[str, asyncio.Task] = {}
        self._stop_events: dict[str, asyncio.Event] = {}
        self._node_operator = NodeOperation(operator_type=OperatorType.SYSTEM)
        self._command_semaphore = asyncio.Semaphore(10)
        self._rpc_semaphore = asyncio.Semaphore(20)
        self._command_handlers: dict[str, callable] = {}
        self._rpc_handlers: dict[str, callable] = {}
        self._register_handlers()

    def register_command_handler(self, action: str, handler):
        self._command_handlers[action] = handler

    def register_rpc_handler(self, action: str, handler):
        self._rpc_handlers[action] = handler

    def _register_handlers(self):
        self.register_command_handler("update_user", self._update_user)
        self.register_command_handler("remove_user", self._remove_user)
        self.register_command_handler("update_users", self._update_users)
        self.register_command_handler("update_node", self._update_node)
        self.register_command_handler("remove_node", self._remove_node)
        self.register_command_handler("connect_node", self._connect_node)
        self.register_command_handler("connect_nodes_bulk", self._connect_nodes_bulk)
        self.register_command_handler("disconnect_node", self._disconnect_node)
        self.register_command_handler("sync_node_users", self._sync_node_users)

        self.register_rpc_handler("get_node_system_stats", self._get_node_system_stats)
        self.register_rpc_handler("get_nodes_system_stats", self._get_nodes_system_stats)
        self.register_rpc_handler("get_user_online_stats", self._get_user_online_stats_by_node)
        self.register_rpc_handler("get_user_ip_list", self._get_user_ip_list_by_node)
        self.register_rpc_handler("get_user_ip_list_all", self._get_user_ip_list_all_nodes)
        self.register_rpc_handler("update_node_api", self._update_node_api)
        self.register_rpc_handler("update_core", self._update_core)
        self.register_rpc_handler("update_geofiles", self._update_geofiles)
        self.register_rpc_handler("start_logs", self._start_logs)

    async def start(self):
        if not IS_NODE_WORKER or not is_nats_enabled():
            return

        self._nc = await create_nats_client()
        if not self._nc:
            return

        self._command_sub = await self._nc.subscribe(NATS_NODE_COMMAND_SUBJECT, cb=self._handle_command)
        self._rpc_sub = await self._nc.subscribe(NATS_NODE_RPC_SUBJECT, cb=self._handle_rpc)
        logger.info("Node worker service started")

    async def stop(self):
        if not IS_NODE_WORKER:
            return

        for stop_event in self._stop_events.values():
            stop_event.set()
        for task in self._log_tasks.values():
            task.cancel()
        self._log_tasks.clear()
        self._stop_events.clear()

        if self._command_sub:
            await self._command_sub.unsubscribe()
            self._command_sub = None
        if self._rpc_sub:
            await self._rpc_sub.unsubscribe()
            self._rpc_sub = None
        if self._nc and not self._nc.is_closed:
            await self._nc.close()
        self._nc = None
        logger.info("Node worker service stopped")

    async def _handle_command(self, msg):
        try:
            payload = json.loads(msg.data.decode())
            action = payload.get("action")
            data = payload.get("payload", {})
        except Exception:
            logger.warning("Invalid node command message")
            return

        asyncio.create_task(self._run_command(action, data))

    async def _handle_rpc(self, msg):
        try:
            payload = json.loads(msg.data.decode())
            action = payload.get("action")
            data = payload.get("payload", {})
        except Exception:
            await msg.respond(json.dumps({"ok": False, "error": "invalid payload"}).encode())
            return

        asyncio.create_task(self._run_rpc(msg, action, data))

    async def _run_command(self, action: str | None, data: dict):
        async with self._command_semaphore:
            try:
                await self._dispatch_command(action, data)
            except Exception as exc:
                logger.error(f"Node command failed: {action} - {exc}", exc_info=True)

    async def _run_rpc(self, msg, action: str | None, data: dict):
        async with self._rpc_semaphore:
            try:
                result = await self._dispatch_rpc(action, data)
                await msg.respond(json.dumps({"ok": True, "data": result}).encode())
            except Exception as exc:
                await msg.respond(json.dumps({"ok": False, "error": str(exc)}).encode())

    async def _dispatch_command(self, action: str | None, data: dict):
        if not action:
            return
        handler = self._command_handlers.get(action)
        if handler:
            await handler(data)

    async def _dispatch_rpc(self, action: str | None, data: dict):
        if not action:
            raise RuntimeError("Unknown action")
        handler = self._rpc_handlers.get(action)
        if not handler:
            raise RuntimeError("Unknown action")
        return await handler(data)

    async def _update_user(self, data: dict):
        username = data.get("username")
        if not username:
            return
        async with GetDB() as db:
            db_user = await get_user(db, username)
            if not db_user:
                return
            user = UserResponse.model_validate(db_user)
            if db_user.status in (UserStatus.active, UserStatus.on_hold):
                inbounds = await db_user.inbounds()
                await node_manager.update_user(user, inbounds)
            else:
                await node_manager.remove_user(user)

    async def _remove_user(self, data: dict):
        username = data.get("username")
        if not username:
            return
        async with GetDB() as db:
            db_user = await get_user(db, username)
            if not db_user:
                return
            user = UserResponse.model_validate(db_user)
            await node_manager.remove_user(user)

    async def _update_users(self, data: dict):
        usernames = data.get("usernames") or []
        if not usernames:
            return
        async with GetDB() as db:
            users = await get_users(db, usernames=usernames)
        await node_manager.update_users(users)

    async def _update_node(self, data: dict):
        node_id = data.get("node_id")
        if not node_id:
            return
        async with GetDB() as db:
            db_node = await get_node_by_id(db, node_id)
        if db_node:
            await node_manager.update_node(db_node)

    async def _remove_node(self, data: dict):
        node_id = data.get("node_id")
        if not node_id:
            return
        await node_manager.remove_node(node_id)

    async def _connect_node(self, data: dict):
        node_id = data.get("node_id")
        if not node_id:
            return
        async with GetDB() as db:
            await self._node_operator.connect_single_node(db, node_id)

    async def _connect_nodes_bulk(self, data: dict):
        node_ids = data.get("node_ids")
        core_id = data.get("core_id")
        async with GetDB() as db:
            if node_ids:
                nodes, _ = await get_nodes(db, ids=node_ids)
            else:
                nodes, _ = await get_nodes(db, enabled=True, core_id=core_id)
            await self._node_operator.connect_nodes_bulk(db, nodes)

    async def _disconnect_node(self, data: dict):
        node_id = data.get("node_id")
        if not node_id:
            return
        await self._node_operator.disconnect_single_node(node_id)

    async def _sync_node_users(self, data: dict):
        node_id = data.get("node_id")
        flush_users = data.get("flush_users", False)
        if not node_id:
            return
        async with GetDB() as db:
            await self._node_operator.sync_node_users(db, node_id=node_id, flush_users=flush_users)

    async def _get_node_system_stats(self, data: dict) -> dict:
        node_id = data.get("node_id")
        if not node_id:
            raise RuntimeError("node_id is required")
        stats = await self._node_operator.get_node_system_stats(node_id)
        return stats.model_dump()

    async def _get_nodes_system_stats(self) -> dict:
        stats = await self._node_operator.get_nodes_system_stats()
        return {node_id: value.model_dump() if value else None for node_id, value in stats.items()}

    async def _get_user_online_stats_by_node(self, data: dict) -> dict:
        node_id = data.get("node_id")
        username = data.get("username")
        if not node_id or not username:
            raise RuntimeError("node_id and username are required")
        async with GetDB() as db:
            return await self._node_operator.get_user_online_stats_by_node(db, node_id, username)

    async def _get_user_ip_list_by_node(self, data: dict) -> dict:
        node_id = data.get("node_id")
        username = data.get("username")
        if not node_id or not username:
            raise RuntimeError("node_id and username are required")
        async with GetDB() as db:
            user_ips = await self._node_operator.get_user_ip_list_by_node(db, node_id, username)
        return user_ips.model_dump()

    async def _get_user_ip_list_all_nodes(self, data: dict) -> dict:
        username = data.get("username")
        if not username:
            raise RuntimeError("username is required")
        async with GetDB() as db:
            user_ips = await self._node_operator.get_user_ip_list_all_nodes(db, username)
        return user_ips.model_dump()

    async def _update_node_api(self, data: dict) -> dict:
        node_id = data.get("node_id")
        if not node_id:
            raise RuntimeError("node_id is required")
        async with GetDB() as db:
            return await self._node_operator.update_node(db, node_id)

    async def _update_core(self, data: dict) -> dict:
        node_id = data.get("node_id")
        payload = data.get("core_update")
        if not node_id or payload is None:
            raise RuntimeError("node_id and core_update are required")
        async with GetDB() as db:
            return await self._node_operator.update_core(db, node_id, NodeCoreUpdate.model_validate(payload))

    async def _update_geofiles(self, data: dict) -> dict:
        node_id = data.get("node_id")
        payload = data.get("geofiles_update")
        if not node_id or payload is None:
            raise RuntimeError("node_id and geofiles_update are required")
        async with GetDB() as db:
            return await self._node_operator.update_geofiles(db, node_id, NodeGeoFilesUpdate.model_validate(payload))

    async def _start_logs(self, data: dict) -> dict:
        node_id = data.get("node_id")
        if not node_id:
            raise RuntimeError("node_id is required")
        node = await node_manager.get_node(node_id)
        if node is None:
            raise RuntimeError("Node not found")

        log_subject = f"{NATS_NODE_LOG_SUBJECT}.{uuid.uuid4().hex}"
        stop_subject = f"{log_subject}.stop"

        stop_event = asyncio.Event()
        self._stop_events[log_subject] = stop_event

        async def _stop_cb(msg):
            stop_event.set()

        await self._nc.subscribe(stop_subject, cb=_stop_cb)

        async def _stream_logs():
            try:
                async with node.stream_logs() as log_queue:
                    while True:
                        done, _ = await asyncio.wait(
                            [log_queue.get(), stop_event.wait()],
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        if stop_event.is_set():
                            break
                        item = done.pop().result()
                        if isinstance(item, NodeAPIError):
                            await self._nc.publish(log_subject, f"Error: {item}".encode())
                            break
                        await self._nc.publish(log_subject, str(item).encode())
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                await self._nc.publish(log_subject, f"Error: {exc}".encode())
            finally:
                self._stop_events.pop(log_subject, None)
                self._log_tasks.pop(log_subject, None)

        self._log_tasks[log_subject] = asyncio.create_task(_stream_logs())

        return {"subject": log_subject, "stop_subject": stop_subject}


node_worker_service = NodeWorkerService()


@on_startup
async def start_node_worker():
    await node_worker_service.start()


@on_shutdown
async def stop_node_worker():
    await node_worker_service.stop()
