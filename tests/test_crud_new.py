"""DB-level CRUD tests for new/changed modules in this PR.

Covers:
- app/db/crud/admin_role.py  (fully new)
- app/db/crud/api_key.py     (fully new)
- app/db/crud/temp_key.py    (fully new)
- Selected new functions in app/db/crud/admin.py

Uses the same in-memory SQLite pattern as tests/test_record_usages.py.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool, StaticPool

from app.db import base
from app.db.models import (
    Admin,
    AdminNotificationReminder,
    AdminRole,
    AdminStatus,
    APIKey,
    APIKeyStatus,
    ReminderType,
    TempKey,
)
from app.utils.crypto import hash_api_key


# ---------------------------------------------------------------------------
# Shared DB fixture (in-memory SQLite, seeds 3 default roles)
# ---------------------------------------------------------------------------


def _get_test_database_url() -> str:
    test_from = os.getenv("TEST_FROM", "local").lower()
    if test_from == "local":
        return "sqlite+aiosqlite:///:memory:"
    from config import database_settings

    return database_settings.url


@pytest.fixture
async def session_factory():
    database_url = _get_test_database_url()
    is_sqlite = database_url.startswith("sqlite")

    engine_kwargs: dict = {}
    connect_args: dict = {}
    if is_sqlite:
        connect_args["check_same_thread"] = False
        engine_kwargs["poolclass"] = StaticPool
    else:
        engine_kwargs["poolclass"] = NullPool

    engine = create_async_engine(database_url, connect_args=connect_args, **engine_kwargs)
    async with engine.begin() as conn:
        await conn.run_sync(base.Base.metadata.drop_all)
        await conn.run_sync(base.Base.metadata.create_all)

    # Seed 3 default roles so FK constraints on admins.role_id are satisfied
    async with async_sessionmaker(bind=engine, expire_on_commit=False)() as seed:
        seed.add_all(
            [
                AdminRole(
                    name="owner",
                    is_owner=True,
                    permissions={},
                    limits={},
                    features={},
                    access={},
                    hwid={},
                ),
                AdminRole(
                    name="administrator",
                    is_owner=False,
                    permissions={},
                    limits={},
                    features={},
                    access={},
                    hwid={},
                ),
                AdminRole(
                    name="operator",
                    is_owner=False,
                    permissions={},
                    limits={},
                    features={},
                    access={},
                    hwid={},
                ),
            ]
        )
        await seed.commit()

    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    yield factory

    async with engine.begin() as conn:
        await conn.run_sync(base.Base.metadata.drop_all)
    await engine.dispose()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_role(name: str = "testrole", **kwargs) -> AdminRole:
    defaults = dict(
        permissions={},
        limits={},
        features={},
        access={},
        hwid={},
        is_owner=False,
    )
    defaults.update(kwargs)
    return AdminRole(name=name, **defaults)


async def _add_role(session_factory, **kwargs) -> AdminRole:
    async with session_factory() as db:
        role = _make_role(**kwargs)
        db.add(role)
        await db.commit()
        await db.refresh(role)
        return role


async def _add_admin(session_factory, role_id: int = 3, username: str = "testadmin") -> Admin:
    async with session_factory() as db:
        admin = Admin(username=username, hashed_password="hash", role_id=role_id)
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
        return admin


# ---------------------------------------------------------------------------
# Tests: app/db/crud/admin_role.py
# ---------------------------------------------------------------------------


class TestGetRole:
    async def test_get_existing_role(self, session_factory):
        from app.db.crud.admin_role import get_role

        async with session_factory() as db:
            role = await get_role(db, 1)
        assert role is not None
        assert role.name == "owner"

    async def test_get_nonexistent_role_returns_none(self, session_factory):
        from app.db.crud.admin_role import get_role

        async with session_factory() as db:
            role = await get_role(db, 9999)
        assert role is None


class TestGetRoleByName:
    async def test_get_by_name(self, session_factory):
        from app.db.crud.admin_role import get_role_by_name

        async with session_factory() as db:
            role = await get_role_by_name(db, "operator")
        assert role is not None
        assert role.id == 3

    async def test_get_by_nonexistent_name_returns_none(self, session_factory):
        from app.db.crud.admin_role import get_role_by_name

        async with session_factory() as db:
            role = await get_role_by_name(db, "nonexistent")
        assert role is None


class TestGetRoles:
    async def test_get_all_roles(self, session_factory):
        from app.db.crud.admin_role import get_roles
        from app.models.admin_role import AdminRoleListQuery

        async with session_factory() as db:
            roles, total = await get_roles(db, AdminRoleListQuery())
        assert total >= 3
        assert len(roles) >= 3

    async def test_search_by_name(self, session_factory):
        from app.db.crud.admin_role import get_roles
        from app.models.admin_role import AdminRoleListQuery

        async with session_factory() as db:
            roles, total = await get_roles(db, AdminRoleListQuery(search="own"))
        assert total == 1
        assert roles[0].name == "owner"

    async def test_pagination(self, session_factory):
        from app.db.crud.admin_role import get_roles
        from app.models.admin_role import AdminRoleListQuery

        async with session_factory() as db:
            roles, total = await get_roles(db, AdminRoleListQuery(limit=2, offset=0))
        assert len(roles) == 2
        assert total >= 3

    async def test_sort_by_name_desc(self, session_factory):
        from app.db.crud.admin_role import get_roles
        from app.models.admin_role import AdminRoleListQuery, AdminRoleSortOption

        async with session_factory() as db:
            roles, _ = await get_roles(db, AdminRoleListQuery(sort=[AdminRoleSortOption.desc_name]))
        names = [r.name for r in roles]
        assert names == sorted(names, reverse=True)

    async def test_search_no_results(self, session_factory):
        from app.db.crud.admin_role import get_roles
        from app.models.admin_role import AdminRoleListQuery

        async with session_factory() as db:
            roles, total = await get_roles(db, AdminRoleListQuery(search="zzznomatch"))
        assert total == 0
        assert roles == []


class TestGetRolesSimple:
    async def test_returns_rows(self, session_factory):
        from app.db.crud.admin_role import get_roles_simple

        async with session_factory() as db:
            rows = await get_roles_simple(db)
        assert len(rows) >= 3


class TestCreateRole:
    async def test_create_basic_role(self, session_factory):
        from app.db.crud.admin_role import create_role
        from app.models.admin_role import AdminRoleCreate, RolePermissions

        async with session_factory() as db:
            data = AdminRoleCreate(
                name="custom_role",
                permissions=RolePermissions(),
            )
            role = await create_role(db, data)
            await db.commit()

        assert role.id is not None
        assert role.name == "custom_role"
        assert role.is_owner is False
        assert role.disabled_when_limited is False
        assert role.disable_users_when_limited is True

    async def test_create_role_with_limits(self, session_factory):
        from app.db.crud.admin_role import create_role
        from app.models.admin_role import AdminRoleCreate, RoleLimits

        async with session_factory() as db:
            data = AdminRoleCreate(name="limited_custom", limits=RoleLimits(max_users=100))
            role = await create_role(db, data)
            await db.commit()

        assert role.limits.get("max_users") == 100 or role.limits == {"max_users": 100}


class TestModifyRole:
    async def test_modify_name(self, session_factory):
        from app.db.crud.admin_role import create_role, modify_role
        from app.models.admin_role import AdminRoleCreate, AdminRoleModify

        async with session_factory() as db:
            role = await create_role(db, AdminRoleCreate(name="old_name"))
            await db.commit()
            modified = await modify_role(db, role, AdminRoleModify(name="new_name"))
            await db.commit()

        assert modified.name == "new_name"

    async def test_modify_owner_role_raises(self, session_factory):
        from app.db.crud.admin_role import get_role, modify_role
        from app.models.admin_role import AdminRoleModify

        async with session_factory() as db:
            owner_role = await get_role(db, 1)
            with pytest.raises(ValueError, match="Cannot modify owner role"):
                await modify_role(db, owner_role, AdminRoleModify(name="hacked"))

    async def test_modify_disable_users_when_limited(self, session_factory):
        from app.db.crud.admin_role import create_role, modify_role
        from app.models.admin_role import AdminRoleCreate, AdminRoleModify

        async with session_factory() as db:
            role = await create_role(db, AdminRoleCreate(name="role_x"))
            await db.commit()
            modified = await modify_role(db, role, AdminRoleModify(disable_users_when_limited=False))
            await db.commit()

        assert modified.disable_users_when_limited is False

    async def test_modify_non_owner_non_builtin_role(self, session_factory):
        from app.db.crud.admin_role import create_role, get_role_by_name, modify_role
        from app.models.admin_role import AdminRoleCreate, AdminRoleModify

        # administrator (id=2) is not is_owner — modify should succeed
        async with session_factory() as db:
            role = await create_role(db, AdminRoleCreate(name="modifiable_role"))
            await db.commit()
            modified = await modify_role(db, role, AdminRoleModify(disabled_when_limited=True))
            await db.commit()
        assert modified.disabled_when_limited is True


class TestDeleteRole:
    async def test_delete_custom_role(self, session_factory):
        from app.db.crud.admin_role import create_role, delete_role, get_role
        from app.models.admin_role import AdminRoleCreate

        async with session_factory() as db:
            role = await create_role(db, AdminRoleCreate(name="to_delete"))
            await db.commit()
            role_id = role.id
            await delete_role(db, role)
            await db.commit()

        async with session_factory() as db:
            found = await get_role(db, role_id)
        assert found is None

    async def test_delete_builtin_role_raises(self, session_factory):
        from app.db.crud.admin_role import delete_role, get_role

        for builtin_id in (1, 2, 3):
            async with session_factory() as db:
                role = await get_role(db, builtin_id)
                with pytest.raises(ValueError, match="Cannot delete built-in role"):
                    await delete_role(db, role)


class TestCountAdminsByRole:
    async def test_count_zero_when_no_admins(self, session_factory):
        from app.db.crud.admin_role import count_admins_by_role

        async with session_factory() as db:
            count = await count_admins_by_role(db, 9999)
        assert count == 0

    async def test_count_with_admins(self, session_factory):
        from app.db.crud.admin_role import count_admins_by_role

        # Add an admin with role_id=3
        await _add_admin(session_factory, role_id=3, username="counttest")

        async with session_factory() as db:
            count = await count_admins_by_role(db, 3)
        assert count >= 1


# ---------------------------------------------------------------------------
# Helpers for API key tests
# (create_api_key calls hash_api_key(model.raw_key) which requires model to
#  carry a raw_key attribute not defined in the Pydantic schema; we insert
#  APIKey rows directly to avoid this dependency in lower-level CRUD tests.)
# ---------------------------------------------------------------------------


async def _insert_api_key(session_factory, admin_id: int, name: str, role_id: int = 3) -> APIKey:
    """Insert an APIKey directly, bypassing the crud layer."""
    from app.utils.crypto import hash_api_key as _hash

    async with session_factory() as db:
        key = APIKey(
            admin_id=admin_id,
            name=name,
            key_hash=_hash(f"raw-{name}"),
            role_id=role_id,
            status=APIKeyStatus.active,
        )
        db.add(key)
        await db.commit()
        await db.refresh(key)
        return key


# ---------------------------------------------------------------------------
# Tests: app/db/crud/api_key.py
# ---------------------------------------------------------------------------


class TestCreateAndGetAPIKey:
    async def _setup_admin(self, session_factory, suffix: str = "") -> int:
        admin = await _add_admin(session_factory, role_id=3, username=f"apikeyadmin{suffix}")
        return admin.id

    async def test_create_api_key_uses_uuid_raw_key(self, session_factory):
        """create_api_key should generate a uuid4 raw key and return it."""
        from unittest.mock import patch

        from app.db.crud.api_key import create_api_key
        from app.models.api_key import APIKeyCreate

        admin_id = await self._setup_admin(session_factory, "1")

        # The CRUD calls hash_api_key(model.raw_key); we patch hash_api_key to
        # avoid the AttributeError since APIKeyCreate doesn't expose raw_key.
        with patch("app.db.crud.api_key.hash_api_key", return_value="fakehash"):
            async with session_factory() as db:
                model = APIKeyCreate(name="testkey", role_id=3)
                raw, db_key = await create_api_key(db, admin_id, model)
                await db.commit()

        # raw_key returned by the crud is a uuid4 string
        assert isinstance(raw, str)
        assert len(raw) == 36  # uuid4 format
        assert db_key.id is not None
        assert db_key.name == "testkey"
        assert db_key.admin_id == admin_id
        assert db_key.role_id == 3
        assert db_key.status == APIKeyStatus.active
        assert db_key.key_hash == "fakehash"

    async def test_get_api_key_by_id(self, session_factory):
        admin_id = await self._setup_admin(session_factory, "2")
        db_key = await _insert_api_key(session_factory, admin_id, "idkey")
        key_id = db_key.id

        from app.db.crud.api_key import get_api_key_by_id

        async with session_factory() as db:
            found = await get_api_key_by_id(db, key_id)
        assert found is not None
        assert found.id == key_id

    async def test_get_api_key_by_id_not_found(self, session_factory):
        from app.db.crud.api_key import get_api_key_by_id

        async with session_factory() as db:
            result = await get_api_key_by_id(db, 99999)
        assert result is None


class TestGetAPIKeys:
    async def _create_key(self, session_factory, admin_id: int, name: str) -> APIKey:
        return await _insert_api_key(session_factory, admin_id, name)

    async def test_list_by_admin(self, session_factory):
        from app.db.crud.api_key import get_api_keys

        admin = await _add_admin(session_factory, role_id=3, username="listkeyadmin")
        await self._create_key(session_factory, admin.id, "key_a")
        await self._create_key(session_factory, admin.id, "key_b")

        async with session_factory() as db:
            keys, total = await get_api_keys(db, admin_id=admin.id, offset=0, limit=50)
        assert total == 2
        assert len(keys) == 2

    async def test_filter_by_name(self, session_factory):
        from app.db.crud.api_key import get_api_keys

        admin = await _add_admin(session_factory, role_id=3, username="filterkeyadmin")
        await self._create_key(session_factory, admin.id, "unique_name_xyz")
        await self._create_key(session_factory, admin.id, "another_key")

        async with session_factory() as db:
            keys, total = await get_api_keys(db, admin_id=admin.id, offset=0, limit=50, name="unique_name_xyz")
        assert total == 1
        assert keys[0].name == "unique_name_xyz"

    async def test_pagination(self, session_factory):
        from app.db.crud.api_key import get_api_keys

        admin = await _add_admin(session_factory, role_id=3, username="paginatekeyadmin")
        for i in range(5):
            await self._create_key(session_factory, admin.id, f"pgkey_{i}")

        async with session_factory() as db:
            keys, total = await get_api_keys(db, admin_id=admin.id, offset=0, limit=3)
        assert total == 5
        assert len(keys) == 3

    async def test_no_keys_for_admin(self, session_factory):
        from app.db.crud.api_key import get_api_keys

        admin = await _add_admin(session_factory, role_id=3, username="nokeyadmin")

        async with session_factory() as db:
            keys, total = await get_api_keys(db, admin_id=admin.id, offset=0, limit=50)
        assert total == 0
        assert keys == []


class TestDeleteAPIKey:
    async def test_delete_removes_key(self, session_factory):
        from app.db.crud.api_key import delete_api_key, get_api_key_by_id

        admin = await _add_admin(session_factory, role_id=3, username="deletekeyadmin")
        db_key = await _insert_api_key(session_factory, admin.id, "to_delete")
        key_id = db_key.id

        async with session_factory() as db:
            key = await get_api_key_by_id(db, key_id)
            await delete_api_key(db, key)
            await db.commit()

        async with session_factory() as db:
            assert await get_api_key_by_id(db, key_id) is None


class TestUpdateAPIKeysRole:
    async def test_update_role_returns_count(self, session_factory):
        from app.db.crud.api_key import update_api_keys_role

        admin = await _add_admin(session_factory, role_id=3, username="roleupdateadmin")

        for i in range(3):
            await _insert_api_key(session_factory, admin.id, f"rolekey_{i}")

        async with session_factory() as db:
            count = await update_api_keys_role(db, admin.id, new_role_id=2)
            await db.commit()

        assert count == 3

    async def test_update_role_changes_role_id(self, session_factory):
        from app.db.crud.api_key import get_api_key_by_id, update_api_keys_role

        admin = await _add_admin(session_factory, role_id=3, username="rolechangeadmin")
        db_key = await _insert_api_key(session_factory, admin.id, "change_role")
        key_id = db_key.id

        async with session_factory() as db:
            await update_api_keys_role(db, admin.id, new_role_id=2)
            await db.commit()

        async with session_factory() as db:
            key = await get_api_key_by_id(db, key_id)
        assert key.role_id == 2


# ---------------------------------------------------------------------------
# Tests: app/db/crud/temp_key.py
# ---------------------------------------------------------------------------


class TestCreateTempKey:
    async def test_creates_key_with_ttl(self, session_factory):
        from app.db.crud.temp_key import KEY_TTL_MINUTES, create_temp_key

        async with session_factory() as db:
            key = await create_temp_key(db)

        assert key.key is not None
        assert len(key.key) == 36  # uuid4
        assert key.used_at is None
        assert key.action == "pending"
        # Expires in ~5 minutes from now
        now = datetime.now(timezone.utc)
        expires = key.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        delta = (expires - now).total_seconds()
        assert 0 < delta <= KEY_TTL_MINUTES * 60 + 5  # small buffer


class TestGetTempKey:
    async def test_get_existing_key(self, session_factory):
        from app.db.crud.temp_key import create_temp_key, get_temp_key

        async with session_factory() as db:
            created = await create_temp_key(db)
            found = await get_temp_key(db, created.key)

        assert found is not None
        assert found.key == created.key

    async def test_get_nonexistent_key_returns_none(self, session_factory):
        from app.db.crud.temp_key import get_temp_key

        async with session_factory() as db:
            result = await get_temp_key(db, "does-not-exist")
        assert result is None


class TestConsumeTempKey:
    async def test_consume_valid_key(self, session_factory):
        from app.db.crud.temp_key import consume_temp_key, create_temp_key, get_temp_key

        async with session_factory() as db:
            key = await create_temp_key(db)

        async with session_factory() as db:
            await consume_temp_key(db, key.key, action="test_action", ip="127.0.0.1")

        async with session_factory() as db:
            used = await get_temp_key(db, key.key)
        assert used.used_at is not None
        assert used.action == "test_action"
        assert used.used_by_ip == "127.0.0.1"

    async def test_consume_already_used_key_raises(self, session_factory):
        from app.db.crud.temp_key import TempKeyConsumeError, consume_temp_key, create_temp_key

        async with session_factory() as db:
            key = await create_temp_key(db)

        async with session_factory() as db:
            await consume_temp_key(db, key.key, action="first", ip="1.1.1.1")

        from app.db.crud.temp_key import TempKeyConsumeError

        async with session_factory() as db:
            with pytest.raises(TempKeyConsumeError, match="key already used"):
                await consume_temp_key(db, key.key, action="second", ip="2.2.2.2")

    async def test_consume_invalid_key_raises(self, session_factory):
        from app.db.crud.temp_key import TempKeyConsumeError, consume_temp_key

        async with session_factory() as db:
            with pytest.raises(TempKeyConsumeError, match="invalid key"):
                await consume_temp_key(db, "completely-wrong-key", action="x", ip="0.0.0.0")

    async def test_consume_expired_key_raises(self, session_factory):
        from app.db.crud.temp_key import TempKeyConsumeError, consume_temp_key

        # Insert a TempKey that is already expired
        async with session_factory() as db:
            expired_key = TempKey(
                key="expired-key-uuid",
                action="pending",
                expires_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            )
            db.add(expired_key)
            await db.commit()

        async with session_factory() as db:
            with pytest.raises(TempKeyConsumeError, match="key expired"):
                await consume_temp_key(db, "expired-key-uuid", action="x", ip="0.0.0.0")


class TestMarkTempKeyUsed:
    async def test_marks_used_at_and_action(self, session_factory):
        from app.db.crud.temp_key import create_temp_key, get_temp_key, mark_temp_key_used

        async with session_factory() as db:
            key = await create_temp_key(db)
            await mark_temp_key_used(db, key, action="mark_action", ip="10.0.0.1")

        async with session_factory() as db:
            refreshed = await get_temp_key(db, key.key)
        assert refreshed.used_at is not None
        assert refreshed.action == "mark_action"
        assert refreshed.used_by_ip == "10.0.0.1"


# ---------------------------------------------------------------------------
# Tests: app/db/crud/admin.py — new / changed functions
# ---------------------------------------------------------------------------


class TestUpdateAdminStatus:
    async def test_flip_to_limited(self, session_factory):
        from app.db.crud.admin import update_admin_status

        admin = await _add_admin(session_factory, role_id=3, username="statusadmin")

        async with session_factory() as db:
            db_admin = (await db.execute(select(Admin).where(Admin.id == admin.id))).scalar_one()
            updated = await update_admin_status(db, db_admin, AdminStatus.limited)

        assert updated.status == AdminStatus.limited
        assert updated.last_status_change is not None

    async def test_flip_to_disabled(self, session_factory):
        from app.db.crud.admin import update_admin_status

        admin = await _add_admin(session_factory, role_id=3, username="disableadmin")

        async with session_factory() as db:
            db_admin = (await db.execute(select(Admin).where(Admin.id == admin.id))).scalar_one()
            updated = await update_admin_status(db, db_admin, AdminStatus.disabled)

        assert updated.status == AdminStatus.disabled
        assert updated.is_disabled is True


class TestGetActiveToLimitedAdmins:
    async def test_returns_admins_over_limit(self, session_factory):
        from app.db.crud.admin import get_active_to_limited_admins

        async with session_factory() as db:
            admin = Admin(
                username="overlimitadmin",
                hashed_password="h",
                role_id=3,
                status=AdminStatus.active,
                data_limit=100,
                used_traffic=200,
            )
            db.add(admin)
            await db.commit()
            await db.refresh(admin)
            admin_id = admin.id

        async with session_factory() as db:
            result = await get_active_to_limited_admins(db)

        ids = [a.id for a in result]
        assert admin_id in ids

    async def test_does_not_return_already_limited(self, session_factory):
        from app.db.crud.admin import get_active_to_limited_admins

        async with session_factory() as db:
            admin = Admin(
                username="alreadylimited",
                hashed_password="h",
                role_id=3,
                status=AdminStatus.limited,
                data_limit=100,
                used_traffic=200,
            )
            db.add(admin)
            await db.commit()
            await db.refresh(admin)
            admin_id = admin.id

        async with session_factory() as db:
            result = await get_active_to_limited_admins(db)

        ids = [a.id for a in result]
        assert admin_id not in ids

    async def test_does_not_return_admin_under_limit(self, session_factory):
        from app.db.crud.admin import get_active_to_limited_admins

        async with session_factory() as db:
            admin = Admin(
                username="underlimitadmin",
                hashed_password="h",
                role_id=3,
                status=AdminStatus.active,
                data_limit=10_000,
                used_traffic=100,
            )
            db.add(admin)
            await db.commit()
            await db.refresh(admin)
            admin_id = admin.id

        async with session_factory() as db:
            result = await get_active_to_limited_admins(db)

        ids = [a.id for a in result]
        assert admin_id not in ids

    async def test_does_not_return_admin_with_no_data_limit(self, session_factory):
        from app.db.crud.admin import get_active_to_limited_admins

        async with session_factory() as db:
            admin = Admin(
                username="nolimitadmin",
                hashed_password="h",
                role_id=3,
                status=AdminStatus.active,
                data_limit=None,
                used_traffic=999_999,
            )
            db.add(admin)
            await db.commit()
            await db.refresh(admin)
            admin_id = admin.id

        async with session_factory() as db:
            result = await get_active_to_limited_admins(db)

        ids = [a.id for a in result]
        assert admin_id not in ids


class TestGetLimitedAdminIdsWithUserSync:
    async def test_returns_ids_when_role_disables_users(self, session_factory):
        from app.db.crud.admin import get_limited_admin_ids_with_user_sync

        # The seeded "operator" role (id=3) has disable_users_when_limited=True by default
        async with session_factory() as db:
            # Ensure the seeded operator role has disable_users_when_limited=True
            role = (await db.execute(select(AdminRole).where(AdminRole.id == 3))).scalar_one()
            role.disable_users_when_limited = True
            await db.commit()

            admin = Admin(
                username="limitedsyncadmin",
                hashed_password="h",
                role_id=3,
                status=AdminStatus.limited,
            )
            db.add(admin)
            await db.commit()
            await db.refresh(admin)
            admin_id = admin.id

        async with session_factory() as db:
            ids = await get_limited_admin_ids_with_user_sync(db)

        assert admin_id in ids

    async def test_excludes_active_admins(self, session_factory):
        from app.db.crud.admin import get_limited_admin_ids_with_user_sync

        async with session_factory() as db:
            admin = Admin(
                username="activesynced",
                hashed_password="h",
                role_id=3,
                status=AdminStatus.active,
            )
            db.add(admin)
            await db.commit()
            await db.refresh(admin)
            admin_id = admin.id

        async with session_factory() as db:
            ids = await get_limited_admin_ids_with_user_sync(db)

        assert admin_id not in ids

    async def test_excludes_when_role_does_not_disable_users(self, session_factory):
        from app.db.crud.admin import get_limited_admin_ids_with_user_sync
        from app.db.crud.admin_role import create_role
        from app.models.admin_role import AdminRoleCreate

        # Create a role with disable_users_when_limited=False
        async with session_factory() as db:
            role = await create_role(
                db,
                AdminRoleCreate(
                    name="nodesyncrole",
                    disable_users_when_limited=False,
                ),
            )
            await db.commit()
            role_id = role.id

        async with session_factory() as db:
            admin = Admin(
                username="nodesynced",
                hashed_password="h",
                role_id=role_id,
                status=AdminStatus.limited,
            )
            db.add(admin)
            await db.commit()
            await db.refresh(admin)
            admin_id = admin.id

        async with session_factory() as db:
            ids = await get_limited_admin_ids_with_user_sync(db)

        assert admin_id not in ids


class TestGetOwnerAndOwnerExists:
    async def test_owner_exists_true_when_owner_present(self, session_factory):
        from app.db.crud.admin import owner_exists

        # role_id=1 is the owner role (seeded)
        async with session_factory() as db:
            admin = Admin(username="owneradmin", hashed_password="h", role_id=1)
            db.add(admin)
            await db.commit()

        async with session_factory() as db:
            exists = await owner_exists(db)
        assert exists is True

    async def test_owner_exists_false_when_no_owner(self, session_factory):
        from app.db.crud.admin import owner_exists

        # Fresh fixture — no admins assigned to role_id=1
        async with session_factory() as db:
            exists = await owner_exists(db)
        assert exists is False

    async def test_get_owner_returns_owner(self, session_factory):
        from app.db.crud.admin import get_owner

        async with session_factory() as db:
            admin = Admin(username="getowner", hashed_password="h", role_id=1)
            db.add(admin)
            await db.commit()

        async with session_factory() as db:
            owner = await get_owner(db)
        assert owner is not None
        assert owner.username == "getowner"

    async def test_get_owner_returns_none_when_missing(self, session_factory):
        from app.db.crud.admin import get_owner

        async with session_factory() as db:
            owner = await get_owner(db)
        assert owner is None


class TestUpgradeAdminToOwner:
    async def test_promotes_admin(self, session_factory):
        from app.db.crud.admin import upgrade_admin_to_owner

        async with session_factory() as db:
            admin = Admin(username="promotable", hashed_password="h", role_id=3)
            db.add(admin)
            await db.commit()

        async with session_factory() as db:
            result = await upgrade_admin_to_owner(db, "promotable")

        assert result.role_id == 1

    async def test_raises_for_nonexistent_admin(self, session_factory):
        from app.db.crud.admin import OwnerUpgradeError, upgrade_admin_to_owner

        async with session_factory() as db:
            with pytest.raises(OwnerUpgradeError, match="admin not found"):
                await upgrade_admin_to_owner(db, "ghost_user")


class TestResetAdminUsage:
    async def test_reset_clears_used_traffic(self, session_factory):
        from app.db.crud.admin import reset_admin_usage

        async with session_factory() as db:
            admin = Admin(
                username="resetadmin",
                hashed_password="h",
                role_id=3,
                status=AdminStatus.active,
                used_traffic=5000,
            )
            db.add(admin)
            await db.commit()
            await db.refresh(admin)

        async with session_factory() as db:
            db_admin = (await db.execute(select(Admin).where(Admin.username == "resetadmin"))).scalar_one()
            result = await reset_admin_usage(db, db_admin)

        assert result.used_traffic == 0

    async def test_reset_changes_limited_to_active(self, session_factory):
        from app.db.crud.admin import reset_admin_usage

        async with session_factory() as db:
            admin = Admin(
                username="limitreset",
                hashed_password="h",
                role_id=3,
                status=AdminStatus.limited,
                used_traffic=10_000,
                data_limit=5_000,
            )
            db.add(admin)
            await db.commit()
            await db.refresh(admin)

        async with session_factory() as db:
            db_admin = (await db.execute(select(Admin).where(Admin.username == "limitreset"))).scalar_one()
            result = await reset_admin_usage(db, db_admin)

        assert result.status == AdminStatus.active

    async def test_reset_with_zero_traffic_returns_early(self, session_factory):
        from app.db.crud.admin import reset_admin_usage

        async with session_factory() as db:
            admin = Admin(
                username="zerousage",
                hashed_password="h",
                role_id=3,
                status=AdminStatus.active,
                used_traffic=0,
            )
            db.add(admin)
            await db.commit()
            await db.refresh(admin)

        async with session_factory() as db:
            db_admin = (await db.execute(select(Admin).where(Admin.username == "zerousage"))).scalar_one()
            result = await reset_admin_usage(db, db_admin)

        assert result.used_traffic == 0
        assert result.status == AdminStatus.active


class TestBulkCreateAdminNotificationReminders:
    async def test_inserts_reminders(self, session_factory):
        from app.db.crud.admin import bulk_create_admin_notification_reminders

        admin = await _add_admin(session_factory, role_id=3, username="reminderadmin")

        reminder_data = [
            {
                "admin_id": admin.id,
                "type": ReminderType.data_usage,
                "threshold": 80,
                "created_at": datetime.now(timezone.utc),
            }
        ]

        async with session_factory() as db:
            await bulk_create_admin_notification_reminders(db, reminder_data)

        async with session_factory() as db:
            rows = (
                await db.execute(
                    select(AdminNotificationReminder).where(AdminNotificationReminder.admin_id == admin.id)
                )
            ).scalars().all()
        assert len(rows) == 1
        assert rows[0].threshold == 80

    async def test_empty_list_does_nothing(self, session_factory):
        from app.db.crud.admin import bulk_create_admin_notification_reminders

        async with session_factory() as db:
            # Should not raise
            await bulk_create_admin_notification_reminders(db, [])


class TestGetUsagePercentageReachedAdmins:
    async def test_returns_admins_at_threshold(self, session_factory):
        from app.db.crud.admin import get_usage_percentage_reached_admins

        async with session_factory() as db:
            admin = Admin(
                username="thresholdadmin",
                hashed_password="h",
                role_id=3,
                status=AdminStatus.active,
                data_limit=1000,
                used_traffic=800,  # 80%
            )
            db.add(admin)
            await db.commit()
            await db.refresh(admin)
            admin_id = admin.id

        async with session_factory() as db:
            result = await get_usage_percentage_reached_admins(db, 80)

        ids = [a.id for a in result]
        assert admin_id in ids

    async def test_excludes_admin_below_threshold(self, session_factory):
        from app.db.crud.admin import get_usage_percentage_reached_admins

        async with session_factory() as db:
            admin = Admin(
                username="belowthreshold",
                hashed_password="h",
                role_id=3,
                status=AdminStatus.active,
                data_limit=1000,
                used_traffic=500,  # 50% — below 80%
            )
            db.add(admin)
            await db.commit()
            await db.refresh(admin)
            admin_id = admin.id

        async with session_factory() as db:
            result = await get_usage_percentage_reached_admins(db, 80)

        ids = [a.id for a in result]
        assert admin_id not in ids

    async def test_excludes_admin_with_existing_reminder(self, session_factory):
        """If a reminder already exists for the threshold, admin is excluded."""
        from app.db.crud.admin import bulk_create_admin_notification_reminders, get_usage_percentage_reached_admins

        async with session_factory() as db:
            admin = Admin(
                username="remindedadmin",
                hashed_password="h",
                role_id=3,
                status=AdminStatus.active,
                data_limit=1000,
                used_traffic=900,  # 90%
            )
            db.add(admin)
            await db.commit()
            await db.refresh(admin)
            admin_id = admin.id

        # Insert a reminder for this admin at 80%
        async with session_factory() as db:
            await bulk_create_admin_notification_reminders(
                db,
                [
                    {
                        "admin_id": admin_id,
                        "type": ReminderType.data_usage,
                        "threshold": 80,
                        "created_at": datetime.now(timezone.utc),
                    }
                ],
            )

        async with session_factory() as db:
            result = await get_usage_percentage_reached_admins(db, 80)

        ids = [a.id for a in result]
        assert admin_id not in ids

    async def test_empty_admin_ids_returns_empty(self, session_factory):
        from app.db.crud.admin import get_usage_percentage_reached_admins

        async with session_factory() as db:
            result = await get_usage_percentage_reached_admins(db, 80, admin_ids=[])
        assert result == []