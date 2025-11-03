import asyncio
from typing import Optional
from pydantic import BaseModel, Field


class TelegramNotification(BaseModel):
    """Model for Telegram notification queue items"""

    message: str
    chat_id: Optional[int] = Field(default=None)
    topic_id: Optional[int] = Field(default=None)
    tries: int = Field(default=0)


class DiscordNotification(BaseModel):
    """Model for Discord notification queue items"""

    json_data: dict
    webhook: str
    tries: int = Field(default=0)


# Global queues for Telegram and Discord notifications
telegram_queue: asyncio.Queue[TelegramNotification] = asyncio.Queue()
discord_queue: asyncio.Queue[DiscordNotification] = asyncio.Queue()


async def enqueue_telegram(message: str, chat_id: Optional[int] = None, topic_id: Optional[int] = None) -> None:
    """Add a Telegram notification to the queue"""
    notification = TelegramNotification(message=message, chat_id=chat_id, topic_id=topic_id)
    await telegram_queue.put(notification)


async def enqueue_discord(json_data: dict, webhook: str) -> None:
    """Add a Discord notification to the queue"""
    notification = DiscordNotification(json_data=json_data, webhook=webhook)
    await discord_queue.put(notification)
