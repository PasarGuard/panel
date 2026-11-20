from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.models.admin import AdminDetails
from app.operation import OperatorType
from app.operation.passkey import PasskeyOperation


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["list", "delete", "register_options", "register_verify"])
async def test_other_admin_cannot_access_owner_passkeys(action):
    operator = PasskeyOperation(OperatorType.API)
    target = SimpleNamespace(id=1, role_id=1)
    admin = AdminDetails(id=2, username="administrator")
    db = AsyncMock()
    with (
        patch("app.operation.passkey.get_passkey_admin", AsyncMock(return_value=target)),
        patch("app.operation.passkey.enforce_permission") as permission,
    ):
        with pytest.raises(HTTPException) as exc:
            if action == "list":
                await operator.list_admin_passkeys(1, admin, db)
            elif action == "delete":
                await operator.delete_admin_passkey(1, 10, admin, db)
            elif action == "register_options":
                await operator.admin_passkey_register_options(1, None, admin, db)
            else:
                await operator.admin_passkey_register_verify(1, None, None, admin, db)
        assert exc.value.status_code == 403
        permission.assert_not_called()
        db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_owner_can_access_own_passkeys():
    operator = PasskeyOperation(OperatorType.API)
    target = SimpleNamespace(id=1, role_id=1)
    admin = AdminDetails(id=1, username="owner")
    with (
        patch("app.operation.passkey.get_passkey_admin", AsyncMock(return_value=target)),
        patch("app.operation.passkey.get_admin_passkeys", AsyncMock(return_value=[])),
        patch("app.operation.passkey.enforce_permission") as permission,
    ):
        assert await operator.list_admin_passkeys(1, admin, AsyncMock()) == []
        permission.assert_not_called()


@pytest.mark.asyncio
async def test_permission_still_allows_access_to_other_non_owner_admin():
    operator = PasskeyOperation(OperatorType.API)
    target = SimpleNamespace(id=3, role_id=2)
    admin = AdminDetails(id=2, username="administrator")
    with (
        patch("app.operation.passkey.get_passkey_admin", AsyncMock(return_value=target)),
        patch("app.operation.passkey.get_admin_passkeys", AsyncMock(return_value=[])),
        patch("app.operation.passkey.enforce_permission") as permission,
    ):
        assert await operator.list_admin_passkeys(3, admin, AsyncMock()) == []
        permission.assert_called_once_with(admin, "admins", "passkeys")
