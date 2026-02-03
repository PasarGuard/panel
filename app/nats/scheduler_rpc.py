import asyncio
import json

import nats
from nats.aio.subscription import Subscription

from app.nats import is_nats_enabled
from app.nats.client import create_nats_client
from app.utils.logger import get_logger
from config import ROLE, NATS_SCHEDULER_RPC_SUBJECT, NATS_SCHEDULER_RPC_TIMEOUT

logger = get_logger("scheduler-nats")


class SchedulerNatsClient:
    def __init__(self):
        self._nc: nats.NATS | None = None
        self._lock = asyncio.Lock()

    async def _get_client(self) -> nats.NATS | None:
        if not is_nats_enabled():
            return None
        if self._nc and not self._nc.is_closed:
            return self._nc
        async with self._lock:
            if self._nc and not self._nc.is_closed:
                return self._nc
            self._nc = await create_nats_client()
            return self._nc

    async def request(self, action: str, payload: dict, timeout: float | None = None) -> dict:
        client = await self._get_client()
        if not client:
            raise RuntimeError("NATS is not available")

        message = {"action": action, "payload": payload}
        timeout = timeout if timeout is not None else NATS_SCHEDULER_RPC_TIMEOUT
        reply = await client.request(NATS_SCHEDULER_RPC_SUBJECT, json.dumps(message).encode(), timeout=timeout)
        response = json.loads(reply.data.decode())

        if not response.get("ok", False):
            error_msg = response.get("error", "Scheduler RPC error")
            error_code = response.get("code", 500)
            exc = RuntimeError(error_msg)
            exc.code = error_code
            raise exc

        return response.get("data")

    async def close(self):
        if self._nc and not self._nc.is_closed:
            await self._nc.close()
        self._nc = None


class SchedulerRpcService:
    def __init__(self):
        self._nc: nats.NATS | None = None
        self._rpc_sub: Subscription | None = None
        self._rpc_semaphore = asyncio.Semaphore(20)
        self._rpc_handlers: dict[str, callable] = {}
        self._register_handlers()

    def _register_handlers(self):
        self._rpc_handlers["health_check"] = self._health_check

    async def start(self):
        if not ROLE.runs_scheduler:
            return
        if ROLE.requires_nats and not is_nats_enabled():
            return

        self._nc = await create_nats_client()
        if not self._nc:
            return

        self._rpc_sub = await self._nc.subscribe(NATS_SCHEDULER_RPC_SUBJECT, cb=self._handle_rpc)
        logger.info("Scheduler RPC service started")

    async def stop(self):
        if not ROLE.runs_scheduler:
            return

        if self._rpc_sub:
            await self._rpc_sub.unsubscribe()
            self._rpc_sub = None
        if self._nc and not self._nc.is_closed:
            await self._nc.close()
        self._nc = None
        logger.info("Scheduler RPC service stopped")

    async def _handle_rpc(self, msg):
        try:
            payload = json.loads(msg.data.decode())
            action = payload.get("action")
            data = payload.get("payload", {})
        except Exception:
            await msg.respond(json.dumps({"ok": False, "error": "invalid payload"}).encode())
            return

        asyncio.create_task(self._run_rpc(msg, action, data))

    async def _run_rpc(self, msg, action: str | None, data: dict):
        async with self._rpc_semaphore:
            try:
                result = await self._dispatch_rpc(action, data)
                await msg.respond(json.dumps({"ok": True, "data": result}).encode())
            except Exception as exc:
                error_msg = str(exc)
                await msg.respond(json.dumps({"ok": False, "error": error_msg, "code": 500}).encode())

    async def _dispatch_rpc(self, action: str | None, data: dict):
        if not action:
            raise RuntimeError("Unknown action")
        handler = self._rpc_handlers.get(action)
        if not handler:
            raise RuntimeError("Unknown action")
        return await handler(data)

    async def _health_check(self, _: dict) -> dict:
        return {"status": "ok"}


scheduler_nats_client = SchedulerNatsClient()
_scheduler_rpc_service = SchedulerRpcService()


async def start_scheduler_rpc():
    await _scheduler_rpc_service.start()


async def stop_scheduler_rpc():
    await _scheduler_rpc_service.stop()
