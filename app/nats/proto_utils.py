"""Utilities for serializing and deserializing Protocol Buffer messages for NATS communication."""

from google.protobuf.json_format import MessageToDict, ParseDict
from google.protobuf.message import Message


def serialize_proto_message(message: Message) -> dict:
    """
    Convert a Protocol Buffer message to a JSON-serializable dictionary.

    Uses the standard protobuf MessageToDict function to ensure compatibility
    with JSON serialization across all NATS node commands.

    Args:
        message: A Protocol Buffer message instance

    Returns:
        A dictionary representation of the message that is JSON-serializable
    """
    return MessageToDict(message, preserving_proto_field_name=True)


def serialize_proto_messages(messages: list[Message]) -> list[dict]:
    """
    Convert a list of Protocol Buffer messages to JSON-serializable dictionaries.

    Args:
        messages: A list of Protocol Buffer message instances

    Returns:
        A list of dictionary representations that are JSON-serializable
    """
    return [serialize_proto_message(msg) for msg in messages]


def deserialize_proto_message(message_dict: dict, message_type: type[Message]) -> Message:
    """
    Convert a dictionary back to a Protocol Buffer message.

    Uses the standard protobuf ParseDict function to handle any proto message type.
    Generic implementation allows reuse for any proto message, not just User.

    Args:
        message_dict: A dictionary representation of a proto message
        message_type: The Protocol Buffer message class to deserialize into (e.g., ProtoUser)

    Returns:
        A Protocol Buffer message instance of the specified type
    """
    return ParseDict(message_dict, message_type())


def deserialize_proto_messages(messages_dicts: list[dict], message_type: type[Message]) -> list[Message]:
    """
    Convert a list of dictionaries back to Protocol Buffer messages.

    Generic implementation allows reuse for any proto message type.

    Args:
        messages_dicts: A list of dictionary representations of proto messages
        message_type: The Protocol Buffer message class to deserialize into (e.g., ProtoUser)

    Returns:
        A list of Protocol Buffer message instances of the specified type
    """
    return [deserialize_proto_message(msg_dict, message_type) for msg_dict in messages_dicts]
