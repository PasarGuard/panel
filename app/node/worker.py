import asyncio
import contextlib
import json
import uuid

from nats.aio.subscription import Subscription
from PasarGuardNodeBridge import NodeAPIError
from PasarGuardNodeBridge.common.service_pb2 import User as ProtoUser

from app import on_shutdown, on_startup
from app.core.manager import core_manager
from app.db import GetDB
from app.db.crud.node import get_node_by_id, get_nodes
from app.db.models import NodeStatus
from app.models.node import NodeCoreUpdate, NodeGeoFilesUpdate, NodeListQuery
from app.nats.node_rpc import CONTROL_NODE_COMMANDS, node_control_subject
from app.nats.proto_utils import deserialize_proto_message, deserialize_proto_messages
from app.nats.rpc_service import BaseRpcService
from app.node import node_manager
from app.operation import OperatorType
from app.operation.node import NodeOperation
from app.utils.logger import get_logger
from config import nats_settings, runtime_settings

logger = get_logger("node-worker")
MAX_PENDING_CONTROL_COMMANDS = 100


class NodeWorkerService(BaseRpcService):
    def __init__(self):
        super().__init__(
            subject=nats_settings.node_rpc_subject,
            logger=logger,
            role_check=lambda: runtime_settings.role.runs_node,
        )
        self._command_sub: Subscription | None = None
        self._control_sub: Subscription | None = None
        self._control_tasks: set[asyncio.Task] = set()
        self._log_tasks: dict[str, asyncio.Task] = {}
        self._stop_events: dict[str, asyncio.Event] = {}
        self._node_operator = NodeOperation(operator_type=OperatorType.SYSTEM)
        self._command_semaphore = asyncio.Semaphore(10)
        self._command_handlers: dict[str, callable] = {}
        self._register_handlers()

    def register_command_handler(self, action: str, handler):
        self._command_handlers[action] = handler

    def _register_handlers(self):
        self.register_command_handler("update_user", self._update_user)
        self.register_command_handler("update_users", self._update_users)
        self.register_command_handler("update_node", self._update_node)
        self.register_command_handler("remove_node", self._remove_node)
        self.register_command_handler("connect_node", self._connect_node)
        self.register_command_handler("connect_nodes_bulk", self._connect_nodes_bulk)
        self.register_command_handler("disconnect_node", self._disconnect_node)
        self.register_command_handler("sync_node_users", self._sync_node_users)

        self.register_rpc_handler("get_node_system_stats", self._get_node_system_stats)
        self.register_rpc_handler("get_nodes_system_stats", self._get_nodes_system_stats)
        self.register_rpc_handler("get_outbounds_latency", self._get_outbounds_latency)
        self.register_rpc_handler("get_user_online_stats", self._get_user_online_stats_by_node)
        self.register_rpc_handler("get_user_ip_list", self._get_user_ip_list_by_node)
        self.register_rpc_handler("get_user_ip_list_all", self._get_user_ip_list_all_nodes)
        self.register_rpc_handler("update_node_api", self._update_node_api)
        self.register_rpc_handler("update_core", self._update_core)
        self.register_rpc_handler("update_geofiles", self._update_geofiles)
        self.register_rpc_handler("start_logs", self._start_logs)

    async def start(self):
        await super().start()
        if not self._nc:
            return

        self._command_sub = await self._nc.subscribe(nats_settings.node_command_subject, cb=self._handle_command)
        # Exactly one worker handles each request, even when several node workers
        # subscribe. Old workers never receive requests on this new subject.
        self._control_sub = await self._nc.subscribe(
            node_control_subject(), queue=f"{node_control_subject()}.workers", cb=self._handle_command
        )
        await self._nc.flush()
        logger.info("Node worker service started")

    async def stop(self):
        if not runtime_settings.role.runs_node:
            return

        for subscription in (self._control_sub, self._command_sub):
            if subscription is not None:
                await subscription.unsubscribe()
        self._control_sub = self._command_sub = None

        command_tasks = list(self._control_tasks)
        for task in command_tasks:
            task.cancel()
        if command_tasks:
            await asyncio.gather(*command_tasks, return_exceptions=True)
        self._control_tasks.clear()

        for stop_event in list(self._stop_events.values()):
            stop_event.set()

        tasks_to_cancel = list(self._log_tasks.values())
        for task in tasks_to_cancel:
            task.cancel()

        # Wait for all cancelled tasks to complete their cleanup
        if tasks_to_cancel:
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
        self._log_tasks.clear()
        self._stop_events.clear()

        await super().stop()
        logger.info("Node worker service stopped")

    async def _handle_command(self, msg):
        """Decode commands and bound pending control work before dispatching."""
        try:
            payload = json.loads(msg.data.decode())
            action = payload.get("action")
            data = payload.get("payload", {})
            if not isinstance(action, str) or not isinstance(data, dict):
                raise TypeError("action must be a string and payload must be an object")
            if msg.reply:
                self._validate_control_payload(action, data)
        except Exception:
            logger.warning("Invalid node command message")
            await self._reply_to_command(msg, error="Invalid node command", code=400)
            return

        if msg.reply and len(self._control_tasks) >= MAX_PENDING_CONTROL_COMMANDS:
            await self._reply_to_command(msg, error="Node control queue is full; retry later", code=503)
            return
        task = asyncio.create_task(self._run_command(action, data, msg))
        if msg.reply:
            self._control_tasks.add(task)
            task.add_done_callback(self._control_tasks.discard)

    @staticmethod
    def _validate_control_payload(action: str, data: dict):
        """Reject malformed selectors before a request can change any node."""
        if action not in CONTROL_NODE_COMMANDS:
            raise ValueError("Unsupported node control command")

        def valid_id(value):
            return type(value) is int and value > 0

        if action == "connect_nodes_bulk":
            if "node_ids" in data:
                if not isinstance(data["node_ids"], list) or any(not valid_id(value) for value in data["node_ids"]):
                    raise ValueError("node_ids must be a list of positive integers")
            elif data.get("core_id") is not None and not valid_id(data["core_id"]):
                raise ValueError("core_id must be a positive integer")
        elif not valid_id(data.get("node_id")):
            raise ValueError("node_id must be a positive integer")
        for key in ("force_start", "stop_first", "flush_users"):
            if key in data and type(data[key]) is not bool:
                raise ValueError(f"{key} must be a boolean")

    @staticmethod
    async def _reply_to_command(msg, *, data=None, error: str | None = None, code: int = 500):
        """Reply only to acknowledged requests, without failing worker cleanup."""
        if not msg.reply:
            return
        response = {"ok": True, "data": data} if error is None else {"ok": False, "error": error, "code": code}
        try:
            await msg.respond(json.dumps(response).encode())
        except Exception as exc:
            logger.warning("Could not confirm node control result: %s", exc)

    async def _run_command(self, action: str | None, data: dict, msg):
        """Acknowledge completion, propagate failures and leave ambiguous work unretried."""
        try:
            async with self._command_semaphore:
                result = await self._dispatch_command(action, data)
            await self._reply_to_command(msg, data=result)
        except asyncio.CancelledError:
            await self._reply_to_command(msg, error="Node worker stopped before command completion", code=503)
            raise
        except Exception as exc:
            logger.exception(f"Node command failed: {action}")
            code = getattr(exc, "status_code", getattr(exc, "code", 500))
            if not isinstance(code, int) or not 400 <= code <= 599:
                code = 500
            await self._reply_to_command(msg, error=str(getattr(exc, "detail", exc)), code=code)

    async def _run_rpc(self, msg, action: str | None, data: dict):
        async with self._rpc_semaphore:
            try:
                result = await self._dispatch_rpc(action, data)
                await msg.respond(json.dumps({"ok": True, "data": result}).encode())
            except Exception as exc:
                error_msg = str(exc)
                # Determine error code based on error message content
                if "NotFound" in error_msg or "not found" in error_msg.lower():
                    error_code = 404
                elif "not allowed" in error_msg.lower() or "permission" in error_msg.lower():
                    error_code = 403
                else:
                    error_code = 500
                await msg.respond(json.dumps({"ok": False, "error": error_msg, "code": error_code}).encode())

    async def _dispatch_command(self, action: str | None, data: dict):
        if not action:
            return
        handler = self._command_handlers.get(action)
        if handler:
            return await handler(data)

    async def _update_user(self, data: dict):
        user_dict = data.get("user")
        if not user_dict:
            return
        proto_user = deserialize_proto_message(user_dict, ProtoUser)
        await node_manager.update_user(proto_user)

    async def _update_users(self, data: dict):
        users_dicts = data.get("users") or []
        if not users_dicts:
            return
        proto_users = deserialize_proto_messages(users_dicts, ProtoUser)
        await node_manager.update_users(proto_users)

    async def _update_node(self, data: dict):
        node_id = data.get("node_id")
        if not node_id:
            return
        async with GetDB() as db:
            db_node = await get_node_by_id(db, node_id, load_usage_logs=False)
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
        # Refresh from KV before connecting to avoid stale core cache races.
        await core_manager._reload_from_cache()
        async with GetDB() as db:
            await self._node_operator.connect_single_node(db, node_id, force_start=bool(data.get("force_start")))

    async def _connect_nodes_bulk(self, data: dict):
        node_ids = data.get("node_ids")
        # An explicitly empty selection must never turn into "all nodes".
        if "node_ids" in data and node_ids == []:
            return
        core_id = data.get("core_id")
        # Refresh from KV before bulk reconnect to avoid stale core cache races.
        await core_manager._reload_from_cache()
        async with GetDB() as db:
            if node_ids:
                nodes, _ = await get_nodes(db, query=NodeListQuery(ids=node_ids), load_usage_logs=False)
            else:
                nodes, _ = await get_nodes(
                    db,
                    query=NodeListQuery(
                        core_id=core_id,
                        status=[NodeStatus.connected, NodeStatus.connecting, NodeStatus.error],
                    ),
                    load_usage_logs=False,
                )
            await self._node_operator.connect_nodes_bulk(
                db,
                nodes,
                force_start=bool(data.get("force_start")),
                # A missing key comes from an API process that predates stop_first.
                stop_first=bool(data.get("stop_first", True)),
            )

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
        # Refresh from KV before syncing to avoid stale core/inbound cache races.
        await core_manager._reload_from_cache()
        async with GetDB() as db:
            result = await self._node_operator.sync_node_users(db, node_id=node_id, flush_users=flush_users)
            return result.model_dump(mode="json")

    async def _get_node_system_stats(self, data: dict) -> dict:
        node_id = data.get("node_id")
        if not node_id:
            raise RuntimeError("node_id is required")
        stats = await self._node_operator.get_node_system_stats(node_id)
        return stats.model_dump()

    async def _get_nodes_system_stats(self, data: dict | None = None) -> dict:
        stats = await self._node_operator.get_nodes_system_stats()
        return {node_id: value.model_dump() if value else None for node_id, value in stats.items()}

    async def _get_outbounds_latency(self, data: dict) -> dict:
        node_id = data.get("node_id")
        if not node_id:
            raise RuntimeError("node_id is required")

        latency = await self._node_operator.get_outbounds_latency(
            node_id=node_id,
            name=data.get("name", ""),
            timeout=data.get("timeout"),
        )
        return latency.model_dump()

    async def _get_user_online_stats_by_node(self, data: dict) -> dict:
        node_id = data.get("node_id")
        user_id = data.get("user_id")
        if not node_id or not user_id:
            raise RuntimeError("node_id and user_id are required")
        async with GetDB() as db:
            return await self._node_operator.get_user_online_stats_by_node(db, node_id, user_id)

    async def _get_user_ip_list_by_node(self, data: dict) -> dict:
        node_id = data.get("node_id")
        user_id = data.get("user_id")
        if not node_id or not user_id:
            raise RuntimeError("node_id and user_id are required")
        async with GetDB() as db:
            user_ips = await self._node_operator.get_user_ip_list_by_node(db, node_id, user_id)
        return user_ips.model_dump()

    async def _get_user_ip_list_all_nodes(self, data: dict) -> dict:
        user_id = data.get("user_id")
        if not user_id:
            raise RuntimeError("user_id is required")
        async with GetDB() as db:
            user_ips = await self._node_operator.get_user_ip_list_all_nodes(db, user_id)
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

        log_subject = f"{nats_settings.node_log_subject}.{uuid.uuid4().hex}"
        stop_subject = f"{log_subject}.stop"

        stop_event = asyncio.Event()
        self._stop_events[log_subject] = stop_event

        async def _stop_cb(msg):
            stop_event.set()

        stop_sub = await self._nc.subscribe(stop_subject, cb=_stop_cb)

        async def _stream_logs():
            try:
                async with node.stream_logs() as log_queue:
                    while not stop_event.is_set():
                        log_task = asyncio.create_task(log_queue.get())
                        wait_task = asyncio.create_task(stop_event.wait())
                        done, pending = await asyncio.wait(
                            [log_task, wait_task],
                            return_when=asyncio.FIRST_COMPLETED,
                        )

                        # Cancel pending tasks to avoid leaks
                        for task in pending:
                            task.cancel()
                            with contextlib.suppress(asyncio.CancelledError):
                                await task

                        if stop_event.is_set():
                            # If we stopped, ensure we don't try to read the log task result if it wasn't the one that finished
                            # Although we verified stop_event is set, log_task might have been cancelled in the pending cleanup
                            break

                        if log_task in done:
                            # log_task completed successfully
                            item = log_task.result()
                            if isinstance(item, NodeAPIError):
                                await self._nc.publish(log_subject, f"Error: {item}".encode())
                                break
                            await self._nc.publish(log_subject, str(item).encode())
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                await self._nc.publish(log_subject, f"Error: {exc}".encode())
            finally:
                with contextlib.suppress(Exception):
                    await stop_sub.unsubscribe()
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
