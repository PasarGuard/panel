from enum import Enum
from typing import Any

from pydantic import BaseModel


class MessageTopic(str, Enum):
    """Enum for message topics/routing targets."""

    CORE = "core"
    HOST = "host"
    SETTING = "setting"
    NODE = "node"  # For future use


class NatsMessage(BaseModel):
    """Structured NATS message format for worker synchronization."""

    topic: MessageTopic
    data: dict[str, Any]
