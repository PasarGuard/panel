from types import SimpleNamespace

import pytest

from app.operation import OperatorType, group as group_operation


@pytest.mark.asyncio
async def test_group_sync_skips_member_revoked_before_dispatch(monkeypatch: pytest.MonkeyPatch):
    """A batch must re-check membership after allocation reconciliation."""
    batches = iter(([1], []))
    dispatched: list[list[int]] = []

    class FakeDB:
        async def commit(self):
            pass

        async def rollback(self):
            pass

    class FakeGetDB:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, exc_type, exc_value, traceback):
            return False

    fake_group = SimpleNamespace(inbound_tags=["inbound"], is_disabled=False)
    fake_user = SimpleNamespace(id=1, admin_id=None)

    async def fake_group_for_sync_update(db, group_id):
        return fake_group

    async def fake_user_ids_batch(db, group_id, *, after_user_id, limit):
        return next(batches)

    async def fake_users_for_node_sync(db, user_ids):
        return [fake_user]

    async def fake_accessible_tags(db, user_ids):
        return {1: {"inbound"}}

    async def fake_allocations(db, users, *, tags_by_user):
        return []

    async def fake_sync_users(users, **kwargs):
        dispatched.append([user.id for user in users])

    async def fake_current_group_users(db, group_id, user_ids):
        return set()

    monkeypatch.setattr(group_operation, "GetDB", FakeGetDB)
    monkeypatch.setattr(group_operation, "get_group_for_sync_update", fake_group_for_sync_update)
    monkeypatch.setattr(group_operation, "get_group_user_ids_batch", fake_user_ids_batch)
    monkeypatch.setattr(group_operation, "get_users_for_node_sync", fake_users_for_node_sync)
    monkeypatch.setattr(group_operation, "get_users_accessible_tags", fake_accessible_tags)
    monkeypatch.setattr(group_operation, "sync_users_allocations", fake_allocations)
    monkeypatch.setattr(group_operation, "get_group_user_ids", fake_current_group_users)
    monkeypatch.setattr(group_operation, "sync_users", fake_sync_users)

    operation = group_operation.GroupOperation(OperatorType.SYSTEM)
    await operation._sync_group_users(
        1,
        expected_inbound_tags=frozenset({"inbound"}),
        expected_is_disabled=False,
    )

    assert dispatched == []
