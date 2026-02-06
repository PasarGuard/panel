import asyncio
import json
from typing import Awaitable, Callable

import nats
from nats.aio.subscription import Subscription

from app.nats import is_nats_enabled
from app.nats.client import create_nats_client
from config import ROLE


class BaseRpcService:
    def __init__(
        self,
        subject: str,
        logger,
        role_check: Callable[[], bool],
        start_msg: str | None = None,
        stop_msg: str | None = None,
        rpc_concurrency: int = 20,
    ):
        self._rpc_subject = subject
        self._logger = logger
        self._role_check = role_check
        self._start_msg = start_msg
        self._stop_msg = stop_msg
        self._nc: nats.NATS | None = None
        self._rpc_sub: Subscription | None = None
        self._rpc_semaphore = asyncio.Semaphore(rpc_concurrency)
        self._rpc_handlers: dict[str, Callable[[dict], Awaitable[dict]]] = {}
        self.register_rpc_handler("health_check", self._health_check)

    def register_rpc_handler(self, action: str, handler):
        self._rpc_handlers[action] = handler

    async def start(self):
        if not self._role_check():
            return
        if ROLE.requires_nats and not is_nats_enabled():
            return

        self._nc = await create_nats_client()
        if not self._nc:
            return

        self._rpc_sub = await self._nc.subscribe(self._rpc_subject, cb=self._handle_rpc)
        if self._start_msg:
            self._logger.info(self._start_msg)

    async def stop(self):
        if not self._role_check():
            return

        if self._rpc_sub:
            await self._rpc_sub.unsubscribe()
            self._rpc_sub = None
        if self._nc and not self._nc.is_closed:
            await self._nc.close()
        self._nc = None
        if self._stop_msg:
            self._logger.info(self._stop_msg)

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
