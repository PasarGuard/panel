import asyncio
import json
from typing import Literal, Optional

import redis.asyncio as redis
from pydantic import BaseModel, Field

from app.core.redis_config import get_redis_config, is_redis_enabled


class NotificationQueue:
    async def enqueue(self, item: dict):
        raise NotImplementedError

    async def dequeue(self, timeout: int | None = None):
        raise NotImplementedError


class RedisNotificationQueue(NotificationQueue):
    def __init__(self, key: str = "notifications:queue"):
        cfg = get_redis_config()
        self.client = redis.Redis(host=cfg["endpoint"], port=cfg["port"], db=cfg["db"])
        self.key = key

    async def enqueue(self, item: dict):
        await self.client.rpush(self.key, json.dumps(item))

    async def dequeue(self, timeout: int | None = 0):
        res = await self.client.blpop(self.key, timeout=timeout or 0)
        if not res:
            return None
        _, data = res
        return json.loads(data)


class InMemoryNotificationQueue(NotificationQueue):
    def __init__(self):
        self.q: asyncio.Queue[dict] = asyncio.Queue()

    async def enqueue(self, item: dict):
        await self.q.put(item)

    async def dequeue(self, timeout: int | None = None):
        if timeout:
            try:
                return await asyncio.wait_for(self.q.get(), timeout=timeout)
            except asyncio.TimeoutError:
                return None
        return await self.q.get()


class TelegramNotification(BaseModel):
    """Model for Telegram notification queue items"""

    type: Literal["telegram"] = Field(default="telegram")
    message: str
    chat_id: Optional[int] = Field(default=None)
    topic_id: Optional[int] = Field(default=None)
    tries: int = Field(default=0)


class DiscordNotification(BaseModel):
    """Model for Discord notification queue items"""

    type: Literal["discord"] = Field(default="discord")
    json_data: dict
    webhook: str
    tries: int = Field(default=0)


queue_instance: NotificationQueue | None = None


def get_queue() -> NotificationQueue:
    global queue_instance
    if queue_instance is None:
        queue_instance = RedisNotificationQueue() if is_redis_enabled() else InMemoryNotificationQueue()
    return queue_instance


async def enqueue_telegram(message: str, chat_id: Optional[int] = None, topic_id: Optional[int] = None) -> None:
    """Add a Telegram notification to the queue"""
    notification = TelegramNotification(message=message, chat_id=chat_id, topic_id=topic_id)
    await get_queue().enqueue(notification.model_dump())


async def enqueue_discord(json_data: dict, webhook: str) -> None:
    """Add a Discord notification to the queue"""
    notification = DiscordNotification(json_data=json_data, webhook=webhook)
    await get_queue().enqueue(notification.model_dump())
