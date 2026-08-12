import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

import jwt
import pytest
from fastapi import HTTPException
from PasarGuardNodeBridge import Health
from PasarGuardNodeBridge.common.service_pb2 import User as ProtoUser
from pydantic import ValidationError

import app.node as node_module
from app.db.models import UserStatus
from app.jobs import remove_expired_users as remove_expired_users_job
from app.models.subscription import SubscriptionUsageQuery
from app.models.user import BulkUsersSelection, ExpiredUsersQuery, UserCreate, UserNotificationResponse
from app.node import NodeManager, sync as node_sync_module
from app.notification import webhook as webhook_notification
from app.operation import OperatorType, admin as admin_operation_module, user as user_operation_module
from app.operation.admin import AdminOperation
from app.operation.subscription import SubscriptionOperation
from app.operation.user import UserOperation
from app.utils import jwt as jwt_utils
from role import Role


def _healthy_runtime_node() -> AsyncMock:
    node = AsyncMock()
    node.get_health.return_value = Health.HEALTHY
    node._supports_chunked_sync.return_value = (True, "0.2.0")
    node.sync_users_chunked.return_value = []
    node.begin_user_revocation = AsyncMock(
        side_effect=lambda user_keys, _revocation_id: SimpleNamespace(
            active_user_keys=tuple(user_keys),
            finalized_user_keys=(),
        )
    )
    node.abort_user_revocation = AsyncMock()
    node.finalize_user_revocation = AsyncMock()
    return node


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [UserStatus.disabled, UserStatus.expired, UserStatus.limited])
async def test_subscription_config_requires_eligible_status(status):
    operation = SubscriptionOperation(operator_type=OperatorType.API)

    with pytest.raises(HTTPException) as exc_info:
        await operation.require_config_eligible(SimpleNamespace(status=status))

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [UserStatus.active, UserStatus.on_hold])
async def test_subscription_config_allows_runtime_eligible_statuses(status):
    operation = SubscriptionOperation(operator_type=OperatorType.API)

    await operation.require_config_eligible(SimpleNamespace(status=status))


@pytest.mark.asyncio
async def test_subscription_usage_rejects_ranges_over_31_days():
    operation = SubscriptionOperation(operator_type=OperatorType.API)
    start = datetime(2026, 1, 1, tzinfo=UTC)

    with pytest.raises(HTTPException) as exc_info:
        await operation.get_user_usage(
            db=None,
            token="unused",
            query=SubscriptionUsageQuery(start=start, end=start + timedelta(days=32)),
        )

    assert exc_info.value.status_code == 400


def test_user_auto_delete_days_are_bounded():
    with pytest.raises(ValidationError):
        UserCreate(username="overflow", auto_delete_in_days=2_147_483_647)


@pytest.mark.asyncio
async def test_admin_tokens_roll_out_expiry_without_rejecting_recent_legacy_tokens(monkeypatch):
    secret = "test-secret"
    monkeypatch.setattr(jwt_utils, "get_secret_key", AsyncMock(return_value=secret))
    monkeypatch.setattr(jwt_utils.jwt_settings, "access_token_expire_minutes", 60)
    recent_legacy_token = jwt.encode(
        {"sub": "admin", "access": "admin", "iat": datetime.now(UTC)},
        secret,
        algorithm="HS256",
    )

    assert await jwt_utils.get_admin_payload(recent_legacy_token) is not None
    issued_token = await jwt_utils.create_admin_token(1, "admin")
    assert "exp" in jwt.decode(issued_token, secret, algorithms=["HS256"])

    expired_legacy_token = jwt.encode(
        {"sub": "admin", "access": "admin", "iat": datetime.now(UTC) - timedelta(hours=2)},
        secret,
        algorithm="HS256",
    )
    assert await jwt_utils.get_admin_payload(expired_legacy_token) is None


@pytest.mark.asyncio
async def test_zero_admin_token_lifetime_preserves_legacy_non_expiring_policy(monkeypatch):
    secret = "test-secret"
    monkeypatch.setattr(jwt_utils, "get_secret_key", AsyncMock(return_value=secret))
    monkeypatch.setattr(jwt_utils.jwt_settings, "access_token_expire_minutes", 0)

    token = await jwt_utils.create_admin_token(1, "admin")

    assert "exp" not in jwt.decode(token, secret, algorithms=["HS256"])
    assert await jwt_utils.get_admin_payload(token) is not None


@pytest.mark.asyncio
async def test_webhook_notification_redacts_subscription_credentials(monkeypatch):
    enqueue = AsyncMock()
    monkeypatch.setattr(
        webhook_notification,
        "webhook_settings",
        AsyncMock(return_value=SimpleNamespace(enable=True)),
    )
    monkeypatch.setattr(webhook_notification, "enqueue_webhook", enqueue)
    user = UserNotificationResponse(
        id=1,
        username="subscriber",
        status=UserStatus.active,
        used_traffic=0,
        created_at=datetime.now(UTC),
        subscription_url="https://example.test/sub/bearer-token",
        proxy_settings={"vless": {"id": "00000000-0000-4000-8000-000000000001"}},
    )

    await webhook_notification.notify(
        webhook_notification.ReachedUsagePercent(
            username=user.username,
            user=user,
            used_percent=80,
        )
    )

    payload = enqueue.await_args.args[0]
    assert "subscription_url" not in payload["user"]
    assert "proxy_settings" not in payload["user"]


@pytest.mark.asyncio
async def test_scheduled_cleanup_revokes_deleted_user_on_nodes(monkeypatch):
    user = SimpleNamespace(id=1, username="expired")
    sync_remove_users = AsyncMock(return_value="scheduled-operation")
    finalize = AsyncMock()

    class FakeDBContext:
        def __init__(self):
            self.db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())

        async def __aenter__(self):
            return self.db

        async def __aexit__(self, exc_type, exc, traceback):
            return None

    db_context = FakeDBContext()
    monkeypatch.setattr(remove_expired_users_job, "GetDB", lambda: db_context)
    remove_users = AsyncMock()
    monkeypatch.setattr(
        remove_expired_users_job,
        "get_autodelete_expired_users_batch",
        AsyncMock(side_effect=[([user], [user], 1), ([], [], None)]),
    )
    monkeypatch.setattr(remove_expired_users_job, "remove_users", remove_users)
    monkeypatch.setattr(remove_expired_users_job, "remove_users_and_wait", sync_remove_users)
    monkeypatch.setattr(remove_expired_users_job, "finalize_users_removal", finalize)
    monkeypatch.setattr(remove_expired_users_job.notification, "remove_user", AsyncMock())

    await remove_expired_users_job.remove_expired_users()

    sync_remove_users.assert_awaited_once_with([user])
    finalize.assert_awaited_once_with("scheduled-operation")
    remove_users.assert_awaited_once_with(db_context.db, [user])


@pytest.mark.asyncio
async def test_scheduled_cleanup_does_not_report_success_when_node_publish_fails(monkeypatch):
    user = SimpleNamespace(id=1, username="expired")

    class FakeDBContext:
        def __init__(self):
            self.db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())

        async def __aenter__(self):
            return self.db

        async def __aexit__(self, exc_type, exc, traceback):
            return None

    db_context = FakeDBContext()
    monkeypatch.setattr(remove_expired_users_job, "GetDB", lambda: db_context)
    monkeypatch.setattr(
        remove_expired_users_job,
        "get_autodelete_expired_users_batch",
        AsyncMock(return_value=([user], [user], 1)),
    )
    monkeypatch.setattr(
        remove_expired_users_job,
        "remove_users_and_wait",
        AsyncMock(side_effect=RuntimeError("node unavailable")),
    )
    notify = AsyncMock()
    monkeypatch.setattr(remove_expired_users_job.notification, "remove_user", notify)

    with pytest.raises(RuntimeError, match="node unavailable"):
        await remove_expired_users_job.remove_expired_users()

    notify.assert_not_called()
    db_context.db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_manual_cleanup_revokes_deleted_user_on_nodes(monkeypatch):
    db_user = SimpleNamespace(id=1, username="expired")
    notification_user = SimpleNamespace(username="expired")
    operation = UserOperation(operator_type=OperatorType.API)
    operation.validate_dates = AsyncMock(return_value=(None, None))
    operation.validate_user = AsyncMock(return_value=notification_user)
    sync_remove_users = AsyncMock(return_value="manual-operation")
    finalize = AsyncMock()
    monkeypatch.setattr(user_operation_module, "get_expired_users", AsyncMock(side_effect=[[db_user], []]))
    monkeypatch.setattr(user_operation_module, "remove_users", AsyncMock())
    monkeypatch.setattr(user_operation_module, "remove_users_and_wait", sync_remove_users)
    monkeypatch.setattr(user_operation_module, "finalize_users_removal", finalize)

    db = SimpleNamespace()
    response = await operation.delete_expired_users(
        db=db,
        admin=SimpleNamespace(username="admin"),
        query=ExpiredUsersQuery(),
    )

    assert response.users == ["expired"]
    sync_remove_users.assert_awaited_once_with([db_user])
    finalize.assert_awaited_once_with("manual-operation")


@pytest.mark.asyncio
async def test_bulk_delete_db_failure_resolves_ambiguous_commit(monkeypatch):
    db_user = SimpleNamespace(id=81, username="bulk-survivor")
    notification_user = SimpleNamespace(id=81, username="bulk-survivor")
    operation = UserOperation(operator_type=OperatorType.API)
    operation._get_validated_users_by_ids = AsyncMock(return_value=[db_user])
    operation.validate_user = AsyncMock(return_value=notification_user)
    revoke = AsyncMock(return_value="bulk-operation")
    resolve = AsyncMock()
    monkeypatch.setattr(user_operation_module, "remove_users_and_wait", revoke)
    monkeypatch.setattr(user_operation_module, "resolve_user_removal_after_db_error", resolve)
    monkeypatch.setattr(
        user_operation_module,
        "remove_users",
        AsyncMock(side_effect=RuntimeError("database commit failed")),
    )

    with pytest.raises(RuntimeError, match="database commit failed"):
        await operation.bulk_remove_users(
            SimpleNamespace(),
            BulkUsersSelection(ids={81}),
            SimpleNamespace(username="admin"),
        )

    revoke.assert_awaited_once_with([db_user])
    resolve.assert_awaited_once_with("bulk-operation", ANY)


@pytest.mark.asyncio
async def test_bulk_delete_success_finalizes_operation_metadata(monkeypatch):
    db_user = SimpleNamespace(id=83, username="bulk-deleted")
    notification_user = SimpleNamespace(id=83, username="bulk-deleted")
    operation = UserOperation(operator_type=OperatorType.API)
    operation._get_validated_users_by_ids = AsyncMock(return_value=[db_user])
    operation.validate_user = AsyncMock(return_value=notification_user)
    finalize = AsyncMock()
    monkeypatch.setattr(user_operation_module, "remove_users_and_wait", AsyncMock(return_value="bulk-commit"))
    monkeypatch.setattr(user_operation_module, "remove_users", AsyncMock())
    monkeypatch.setattr(user_operation_module, "finalize_users_removal", finalize)

    await operation.bulk_remove_users(
        SimpleNamespace(), BulkUsersSelection(ids={83}), SimpleNamespace(username="admin")
    )

    finalize.assert_awaited_once_with("bulk-commit")


@pytest.mark.asyncio
async def test_admin_delete_success_finalizes_operation_metadata(monkeypatch):
    db_user = SimpleNamespace(id=84, username="admin-owned")
    notification_user = SimpleNamespace(id=84, username="admin-owned")
    operation = AdminOperation(operator_type=OperatorType.API)
    finalize = AsyncMock()
    monkeypatch.setattr(admin_operation_module, "get_users", AsyncMock(return_value=[db_user]))
    monkeypatch.setattr(
        admin_operation_module.UserOperation, "validate_user", AsyncMock(return_value=notification_user)
    )
    monkeypatch.setattr(admin_operation_module, "remove_users_and_wait", AsyncMock(return_value="admin-commit"))
    monkeypatch.setattr(admin_operation_module, "remove_users", AsyncMock())
    monkeypatch.setattr(admin_operation_module, "finalize_users_removal", finalize)

    await operation._remove_all_users_for_admin(
        SimpleNamespace(), SimpleNamespace(username="owner"), SimpleNamespace(username="admin")
    )

    finalize.assert_awaited_once_with("admin-commit")


@pytest.mark.asyncio
async def test_bulk_delete_late_remote_chunk_failure_aborts_fences_before_database_delete(monkeypatch):
    manager = NodeManager()
    users = [
        UserNotificationResponse(
            id=user_id,
            username=f"user-{user_id}",
            status=UserStatus.active,
            used_traffic=0,
            created_at=datetime.now(UTC),
            proxy_settings={"vless": {"id": f"00000000-0000-4000-8000-{user_id:012d}"}},
        )
        for user_id in (101, 102)
    ]
    operation = UserOperation(operator_type=OperatorType.API)
    operation._get_validated_users_by_ids = AsyncMock(
        return_value=[
            SimpleNamespace(
                id=user.id,
                sync_id=f"sync-{user.id}",
                username=user.username,
                proxy_settings=user.proxy_settings.dict(),
                status=UserStatus.active,
                groups=[],
            )
            for user in users
        ]
    )
    operation.validate_user = AsyncMock(side_effect=users)
    database_delete = AsyncMock()

    async def remote_request(action, payload):
        user_keys = {user["email"] for user in payload["users"]}
        revocation_id = payload["revocation_id"]
        if action == "revoke_users":
            if user_keys == {"sync-102"}:
                raise RuntimeError("second chunk failed")
            manager._acquire_deletion_fences(user_keys, revocation_id)
            return {}
        assert action == "abort_revoke_users"
        manager._release_deletion_fences(user_keys, revocation_id)
        return {}

    monkeypatch.setattr(node_sync_module.runtime_settings, "role", Role.BACKEND)
    monkeypatch.setattr(node_sync_module.nats_settings, "node_update_users_batch_size", 1)
    monkeypatch.setattr(node_sync_module.node_nats_client, "request", remote_request)
    monkeypatch.setattr(user_operation_module, "remove_users", database_delete)

    with pytest.raises(node_sync_module.NodeRevocationError, match="second chunk failed"):
        await operation.bulk_remove_users(
            SimpleNamespace(),
            BulkUsersSelection(ids={101, 102}),
            SimpleNamespace(username="admin"),
        )

    database_delete.assert_not_awaited()
    assert manager._deleted_user_keys == set()
    assert manager._deletion_fence_owners == {}


@pytest.mark.asyncio
async def test_bulk_delete_child_cancelled_node_does_not_delete_database_rows(monkeypatch):
    manager = NodeManager()
    manager._nodes = {1: _healthy_runtime_node(), 2: _healthy_runtime_node()}
    user = UserNotificationResponse(
        id=103,
        username="child-cancelled-user",
        status=UserStatus.active,
        used_traffic=0,
        created_at=datetime.now(UTC),
        proxy_settings={"vless": {"id": "00000000-0000-4000-8000-000000000103"}},
    )
    operation = UserOperation(operator_type=OperatorType.API)
    operation._get_validated_users_by_ids = AsyncMock(
        return_value=[SimpleNamespace(id=user.id, username=user.username)]
    )
    operation.validate_user = AsyncMock(return_value=user)
    database_delete = AsyncMock()

    async def sync_node(node_id, _node, _users, **_kwargs):
        if node_id == 2:
            raise asyncio.CancelledError

    async def revoke_users(users):
        proto_users = [ProtoUser(email=str(item.id)) for item in users]
        return await manager.revoke_users_and_wait(proto_users, "bulk-child-cancel")

    monkeypatch.setattr(manager, "_sync_users_to_node", sync_node)
    monkeypatch.setattr(user_operation_module, "remove_users_and_wait", revoke_users)
    monkeypatch.setattr(user_operation_module, "remove_users", database_delete)

    with pytest.raises(node_sync_module.NodeRevocationError, match="failed to sync users to 1/2 nodes"):
        await operation.bulk_remove_users(
            SimpleNamespace(),
            BulkUsersSelection(ids={103}),
            SimpleNamespace(username="admin"),
        )

    database_delete.assert_not_awaited()
    assert manager._deleted_user_keys == set()
    assert manager._deletion_fence_owners == {}


@pytest.mark.asyncio
async def test_manual_expired_delete_db_failure_resolves_ambiguous_commit(monkeypatch):
    db_user = SimpleNamespace(id=82, username="expired-survivor")
    notification_user = SimpleNamespace(id=82, username="expired-survivor")
    operation = UserOperation(operator_type=OperatorType.API)
    operation.validate_dates = AsyncMock(return_value=(None, None))
    operation.validate_user = AsyncMock(return_value=notification_user)
    resolve = AsyncMock()
    monkeypatch.setattr(user_operation_module, "get_expired_users", AsyncMock(return_value=[db_user]))
    monkeypatch.setattr(user_operation_module, "remove_users_and_wait", AsyncMock(return_value="expired-operation"))
    monkeypatch.setattr(user_operation_module, "resolve_user_removal_after_db_error", resolve)
    monkeypatch.setattr(
        user_operation_module,
        "remove_users",
        AsyncMock(side_effect=RuntimeError("database commit failed")),
    )

    with pytest.raises(RuntimeError, match="database commit failed"):
        await operation.delete_expired_users(
            db=SimpleNamespace(),
            admin=SimpleNamespace(username="admin"),
            query=ExpiredUsersQuery(),
        )

    resolve.assert_awaited_once_with("expired-operation", ANY)


@pytest.mark.asyncio
async def test_single_delete_db_failure_aborts_fence_and_allows_future_sync(monkeypatch):
    manager = NodeManager()
    monkeypatch.setattr(node_sync_module.runtime_settings, "role", Role.ALL_IN_ONE)
    monkeypatch.setattr(node_sync_module, "node_manager", manager)
    db_user = SimpleNamespace(
        id=91,
        sync_id="sync-91",
        username="surviving-user",
        proxy_settings={"vless": {"id": "00000000-0000-4000-8000-000000000091"}},
        status=UserStatus.active,
        groups=[],
    )
    notification_user = UserNotificationResponse(
        id=91,
        username="surviving-user",
        status=UserStatus.active,
        used_traffic=0,
        created_at=datetime.now(UTC),
        proxy_settings={"vless": {"id": "00000000-0000-4000-8000-000000000091"}},
    )
    operation = UserOperation(operator_type=OperatorType.API)
    operation.validate_user = AsyncMock(return_value=notification_user)
    row_exists = True

    async def fail_database_delete(*_args, **_kwargs):
        raise RuntimeError("database commit failed")

    monkeypatch.setattr(user_operation_module, "remove_user", fail_database_delete)

    async def resolve_present(revocation, _db):
        await node_sync_module.abort_user_removal(revocation)

    monkeypatch.setattr(user_operation_module, "resolve_user_removal_after_db_error", resolve_present)

    with pytest.raises(RuntimeError, match="database commit failed"):
        await operation._remove_user(SimpleNamespace(), db_user, SimpleNamespace(username="admin"))

    assert row_exists is True
    assert "sync-91" not in manager._deleted_user_keys
    node = AsyncMock()
    manager._nodes[1] = node
    await manager.update_user(
        node_sync_module._serialize_user_for_node("sync-91", notification_user.proxy_settings.dict())
    )
    node.update_user.assert_awaited_once()


@pytest.mark.asyncio
async def test_single_delete_db_failure_restores_exact_original_node_state(monkeypatch):
    manager = NodeManager()
    node = _healthy_runtime_node()
    manager._nodes = {1: node}
    monkeypatch.setattr(node_sync_module.runtime_settings, "role", Role.ALL_IN_ONE)
    monkeypatch.setattr(node_sync_module, "node_manager", manager)
    group = SimpleNamespace(
        is_disabled=False,
        inbounds=[SimpleNamespace(tag="vless-in")],
    )
    db_user = SimpleNamespace(
        id=191,
        sync_id="sync-191",
        username="surviving-user",
        proxy_settings={"vless": {"id": "00000000-0000-4000-8000-000000000191"}},
        status=UserStatus.active,
        groups=[group],
    )
    notification_user = UserNotificationResponse(
        id=191,
        username="surviving-user",
        status=UserStatus.active,
        used_traffic=0,
        created_at=datetime.now(UTC),
        proxy_settings=db_user.proxy_settings,
    )
    operation = UserOperation(operator_type=OperatorType.API)
    operation.validate_user = AsyncMock(return_value=notification_user)
    applied: list[tuple[str, ...]] = []

    async def sync_batch(_node, users, *, revocation_id=None):
        assert revocation_id
        applied.append(tuple(users[0].inbounds))
        return 0

    monkeypatch.setattr(manager, "_sync_user_batch_to_node", sync_batch)
    monkeypatch.setattr(
        user_operation_module,
        "remove_user",
        AsyncMock(side_effect=RuntimeError("database commit failed")),
    )

    async def resolve_present(revocation, _db):
        await node_sync_module.abort_user_removal(revocation)

    monkeypatch.setattr(user_operation_module, "resolve_user_removal_after_db_error", resolve_present)

    with pytest.raises(RuntimeError, match="database commit failed"):
        await operation._remove_user(SimpleNamespace(), db_user, SimpleNamespace(username="admin"))

    assert applied == [(), ("vless-in",)]
    node.abort_user_revocation.assert_awaited_once_with(["sync-191"], ANY)
    node.update_users.assert_awaited_once()
    assert node.update_users.await_args.args[0][0].inbounds == ["vless-in"]
    assert manager._deleted_user_keys == set()
    assert manager._deletion_fence_owners == {}


@pytest.mark.asyncio
async def test_single_delete_success_keeps_permanent_fence(monkeypatch):
    monkeypatch.setattr(node_module, "needs_shared_bridge_memory", lambda: False)
    manager = NodeManager()
    monkeypatch.setattr(node_sync_module.runtime_settings, "role", Role.ALL_IN_ONE)
    monkeypatch.setattr(node_sync_module, "node_manager", manager)
    db_user = SimpleNamespace(
        id=92,
        sync_id="sync-92",
        username="deleted-user",
        proxy_settings={"vless": {"id": "00000000-0000-4000-8000-000000000092"}},
        status=UserStatus.active,
        groups=[],
    )
    notification_user = UserNotificationResponse(
        id=92,
        username="deleted-user",
        status=UserStatus.active,
        used_traffic=0,
        created_at=datetime.now(UTC),
        proxy_settings={"vless": {"id": "00000000-0000-4000-8000-000000000092"}},
    )
    operation = UserOperation(operator_type=OperatorType.API)
    operation.validate_user = AsyncMock(return_value=notification_user)
    monkeypatch.setattr(user_operation_module, "remove_user", AsyncMock())
    monkeypatch.setattr(user_operation_module.notification, "remove_user", AsyncMock())

    await operation._remove_user(SimpleNamespace(), db_user, SimpleNamespace(username="admin"))

    assert "sync-92" in manager._deleted_user_keys
    assert manager._deletion_fence_owners == {}
