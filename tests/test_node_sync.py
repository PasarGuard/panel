from copy import deepcopy
from itertools import chain
from unittest.mock import Mock

import pytest

from app.nats.node_rpc import encode_node_command
from app.node import sync as node_sync_module


def test_node_update_users_nats_chunks_respect_payload_limit(monkeypatch: pytest.MonkeyPatch):
    users = [{"email": f"user-{index}", "payload": "x" * 600} for index in range(5)]
    max_payload = len(encode_node_command("update_users", {"users": users[:2]}))

    monkeypatch.setattr(node_sync_module.nats_settings, "node_update_users_batch_size", 100)
    monkeypatch.setattr(node_sync_module.nats_settings, "node_command_max_payload_bytes", max_payload)

    chunks = node_sync_module._chunk_serialized_users_for_nats(users)

    assert [len(chunk) for chunk in chunks] == [2, 2, 1]
    assert all(len(encode_node_command("update_users", {"users": chunk})) <= max_payload for chunk in chunks)


@pytest.mark.parametrize("padding", ["x" * 600, 'کاربر😀\\"\n' * 80])
@pytest.mark.parametrize("limit_delta", [-1, 0, 1])
def test_node_update_users_nats_chunks_at_exact_byte_boundary(monkeypatch, padding, limit_delta):
    users = [
        {"email": f"user-{index}", "config": {"inbounds": [padding], "enabled": True, "optional": None}}
        for index in range(5)
    ]
    original_users = deepcopy(users)
    max_payload = len(encode_node_command("update_users", {"users": users[:2]})) + limit_delta
    monkeypatch.setattr(node_sync_module.nats_settings, "node_update_users_batch_size", 100)
    monkeypatch.setattr(node_sync_module.nats_settings, "node_command_max_payload_bytes", max_payload)

    chunks = node_sync_module._chunk_serialized_users_for_nats(users)

    assert [len(chunk) for chunk in chunks] == ([1] * 5 if limit_delta < 0 else [2, 2, 1])
    assert all(len(encode_node_command("update_users", {"users": chunk})) <= max_payload for chunk in chunks)
    assert users == original_users
    assert all(actual is expected for actual, expected in zip(chain.from_iterable(chunks), users, strict=True))


@pytest.mark.parametrize("batch_size,expected_sizes", [(2, [2, 2, 1]), (1, [1] * 5), (0, [1] * 5), (-1, [1] * 5)])
def test_node_update_users_nats_chunks_respect_batch_size(monkeypatch, batch_size, expected_sizes):
    users = [{"email": f"user-{index}"} for index in range(5)]
    monkeypatch.setattr(node_sync_module.nats_settings, "node_update_users_batch_size", batch_size)
    monkeypatch.setattr(node_sync_module.nats_settings, "node_command_max_payload_bytes", 900_000)

    chunks = node_sync_module._chunk_serialized_users_for_nats(users)

    assert [len(chunk) for chunk in chunks] == expected_sizes
    assert list(chain.from_iterable(chunks)) == users


@pytest.mark.parametrize("configured_limit", [-1, 0, 1024])
def test_node_update_users_nats_chunks_keep_minimum_payload_limit(monkeypatch, configured_limit):
    users = [{"email": f"user-{index}", "payload": "x" * 360} for index in range(5)]
    monkeypatch.setattr(node_sync_module.nats_settings, "node_update_users_batch_size", 100)
    monkeypatch.setattr(node_sync_module.nats_settings, "node_command_max_payload_bytes", configured_limit)

    chunks = node_sync_module._chunk_serialized_users_for_nats(users)

    assert [len(chunk) for chunk in chunks] == [2, 2, 1]
    assert all(len(encode_node_command("update_users", {"users": chunk})) <= 1024 for chunk in chunks)


def test_node_update_users_nats_chunks_preserve_oversized_single_user(monkeypatch):
    users = [{"email": "before"}, {"email": "oversized", "payload": "x" * 2000}, {"email": "after"}]
    monkeypatch.setattr(node_sync_module.nats_settings, "node_update_users_batch_size", 100)
    monkeypatch.setattr(node_sync_module.nats_settings, "node_command_max_payload_bytes", 1024)
    warning = Mock()
    monkeypatch.setattr(node_sync_module.logger, "warning", warning)

    chunks = node_sync_module._chunk_serialized_users_for_nats(users)

    assert chunks == [[users[0]], [users[1]], [users[2]]]
    warning.assert_called_once()
    assert warning.call_args.args[1] == "oversized"


def test_node_update_users_nats_chunks_skip_encoding_empty_input(monkeypatch):
    encoder = Mock(wraps=encode_node_command)
    monkeypatch.setattr(node_sync_module, "encode_node_command", encoder)

    assert node_sync_module._chunk_serialized_users_for_nats([]) == []
    encoder.assert_not_called()


def test_node_update_users_nats_chunk_sizing_encodes_each_user_once(monkeypatch):
    users = [{"email": f"user-{index}", "payload": "x" * 600} for index in range(1000)]
    monkeypatch.setattr(node_sync_module.nats_settings, "node_update_users_batch_size", 100)
    monkeypatch.setattr(node_sync_module.nats_settings, "node_command_max_payload_bytes", 900_000)
    encoded_users = 0
    encode_calls = 0

    def counted_encoder(action, payload):
        nonlocal encoded_users, encode_calls
        encoded_users += len(payload["users"])
        encode_calls += 1
        return encode_node_command(action, payload)

    monkeypatch.setattr(node_sync_module, "encode_node_command", counted_encoder)

    chunks = node_sync_module._chunk_serialized_users_for_nats(users)

    assert [len(chunk) for chunk in chunks] == [100] * 10
    assert list(chain.from_iterable(chunks)) == users
    assert encoded_users == len(users)
    assert encode_calls <= len(users) + 1
