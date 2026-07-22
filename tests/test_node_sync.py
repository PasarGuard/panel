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
