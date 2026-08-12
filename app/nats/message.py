from enum import Enum
from typing import Any

from pydantic import BaseModel


class MessageTopic(str, Enum):
    """Enum for message topics/routing targets."""

    CORE = "core"
    HOST = "host"
    SETTING = "setting"
    CLIENT_TEMPLATE = "client_template"
    NODE = "node"
    NODE_ONLINE = "node_online"


class NatsMessage(BaseModel):
    """Structured NATS message format for worker synchronization."""

    topic: MessageTopic
    data: dict[str, Any]
