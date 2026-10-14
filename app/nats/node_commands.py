"""Durable delivery of user commands to a node worker."""

import hashlib

from nats.js.api import AckPolicy, ConsumerConfig, DiscardPolicy, RetentionPolicy, StorageType
from nats.js.errors import APIError, NotFoundError

from config import nats_settings

USER_COMMANDS = frozenset({"update_user", "update_users"})
COMMAND_ACK_WAIT = 120.0
COMMAND_CONCURRENCY = 10


def user_command_subject() -> str:
    # Separate from legacy Core NATS commands to avoid processing each update twice.
    return f"{nats_settings.node_command_subject}.users"


def user_command_stream() -> str:
    digest = hashlib.sha256(user_command_subject().encode()).hexdigest()[:16].upper()
    return f"PG_NODE_USERS_{digest}"


async def ensure_user_command_stream(js) -> str:
    name = user_command_stream()
    subject = user_command_subject()
    try:
        info = await js.stream_info(name)
    except NotFoundError:
        try:
            info = await js.add_stream(
                name=name,
                subjects=[subject],
                retention=RetentionPolicy.WORK_QUEUE,
                storage=StorageType.FILE,
                discard=DiscardPolicy.NEW,
                duplicate_window=120,
            )
        except APIError:
            # Another publisher/worker may have created the same stream concurrently.
            info = await js.stream_info(name)
    if info.config.subjects != [subject] or info.config.retention != RetentionPolicy.WORK_QUEUE:
        raise RuntimeError(f"Unexpected configuration for node user command stream {name}")
    return name


async def subscribe_user_commands(js):
    stream = await ensure_user_command_stream(js)
    return await js.pull_subscribe(
        user_command_subject(),
        stream=stream,
        durable="node_users",
        config=ConsumerConfig(
            ack_policy=AckPolicy.EXPLICIT,
            ack_wait=COMMAND_ACK_WAIT,
            max_ack_pending=COMMAND_CONCURRENCY,
        ),
    )
