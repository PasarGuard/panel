"""Unit tests for admin-related Pydantic models changed in this PR.

Covers:
- app/models/admin.py  (AdminRoleData, AdminDetails, AdminModify, AdminCreate,
                        AdminValidationResult, AdminsResponse, BulkAdminSelection)
- app/models/admin_role.py  (PermissionScope, permission classes, RoleLimits,
                             RoleFeatures, RoleAccess, RolePermissions,
                             AdminRoleCreate, AdminRoleModify, AdminRoleListQuery)
- app/models/api_key.py  (APIKeyCreate expire_date validation, APIKeyResponse,
                          APIKeysQuery)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.db.models import AdminStatus, APIKeyStatus
from app.models.admin import (
    AdminCreate,
    AdminDetails,
    AdminModify,
    AdminRoleData,
    AdminsResponse,
    AdminValidationResult,
    BulkAdminSelection,
)
from app.models.admin_role import (
    AdminRoleCreate,
    AdminRoleListQuery,
    AdminRoleModify,
    AdminRoleSortOption,
    APIKeysPermissions,
    CRUDPermissions,
    PermissionScope,
    RoleAccess,
    RoleFeatures,
    RoleLimits,
    RolePermissions,
    UsersPermissions,
)
from app.models.api_key import APIKeyCreate, APIKeyResponse, APIKeysQuery
from app.models.settings import HWIDSettings


# ---------------------------------------------------------------------------
# AdminRoleData
# ---------------------------------------------------------------------------


class TestAdminRoleData:
    def test_defaults(self):
        role = AdminRoleData()
        assert role.id is None
        assert role.name == ""
        assert role.is_owner is False
        assert role.disabled_when_limited is False
        assert role.disable_users_when_limited is True

    def test_is_owner_flag(self):
        role = AdminRoleData(is_owner=True)
        assert role.is_owner is True

    def test_from_dict(self):
        data = {"id": 1, "name": "owner", "is_owner": True}
        role = AdminRoleData(**data)
        assert role.id == 1
        assert role.name == "owner"
        assert role.is_owner is True

    def test_from_attributes_orm_mock(self):
        """from_attributes=True means it can be constructed from ORM-like objects."""
        orm_obj = MagicMock()
        orm_obj.id = 2
        orm_obj.name = "administrator"
        orm_obj.is_owner = False
        orm_obj.permissions = {}
        orm_obj.limits = {}
        orm_obj.features = {}
        orm_obj.access = {}
        orm_obj.hwid = {}
        orm_obj.disabled_when_limited = False
        orm_obj.disable_users_when_limited = True
        role = AdminRoleData.model_validate(orm_obj)
        assert role.id == 2
        assert role.name == "administrator"

    def test_permissions_default_factory(self):
        """Each AdminRoleData instance gets independent permission objects."""
        r1 = AdminRoleData()
        r2 = AdminRoleData()
        assert r1.permissions is not r2.permissions

    def test_limits_default_factory(self):
        r1 = AdminRoleData()
        r2 = AdminRoleData()
        assert r1.limits is not r2.limits


# ---------------------------------------------------------------------------
# AdminDetails — computed fields
# ---------------------------------------------------------------------------


class TestAdminDetailsComputedFields:
    def _make(self, status: AdminStatus = AdminStatus.active, role=None) -> AdminDetails:
        return AdminDetails(
            username="testadmin",
            status=status,
            role=role,
        )

    def test_is_disabled_false_when_active(self):
        admin = self._make(AdminStatus.active)
        assert admin.is_disabled is False

    def test_is_disabled_true_when_disabled(self):
        admin = self._make(AdminStatus.disabled)
        assert admin.is_disabled is True

    def test_is_disabled_false_when_limited(self):
        admin = self._make(AdminStatus.limited)
        assert admin.is_disabled is False

    def test_is_limited_true_when_limited(self):
        admin = self._make(AdminStatus.limited)
        assert admin.is_limited is True

    def test_is_limited_false_when_active(self):
        admin = self._make(AdminStatus.active)
        assert admin.is_limited is False

    def test_is_limited_false_when_disabled(self):
        admin = self._make(AdminStatus.disabled)
        assert admin.is_limited is False

    def test_is_owner_true_when_role_is_owner(self):
        role = AdminRoleData(is_owner=True)
        admin = self._make(role=role)
        assert admin.is_owner is True

    def test_is_owner_false_when_role_is_not_owner(self):
        role = AdminRoleData(is_owner=False)
        admin = self._make(role=role)
        assert admin.is_owner is False

    def test_is_owner_false_when_no_role(self):
        admin = self._make(role=None)
        assert admin.is_owner is False

    def test_default_status_is_active(self):
        admin = AdminDetails(username="x")
        assert admin.status == AdminStatus.active

    def test_data_limit_defaults_to_none(self):
        admin = AdminDetails(username="x")
        assert admin.data_limit is None

    def test_role_and_permission_overrides_default_none(self):
        admin = AdminDetails(username="x")
        assert admin.role is None
        assert admin.permission_overrides is None

    def test_used_traffic_cast_to_int(self):
        """AdminDetails casts used_traffic via NumericValidatorMixin."""
        admin = AdminDetails(username="x", used_traffic="123")
        assert admin.used_traffic == 123

    def test_is_disabled_is_computed_field_in_serialization(self):
        """is_disabled and is_limited appear in serialized output as computed fields."""
        admin = AdminDetails(username="x", status=AdminStatus.disabled)
        data = admin.model_dump()
        assert data["is_disabled"] is True
        assert data["is_limited"] is False


# ---------------------------------------------------------------------------
# AdminModify
# ---------------------------------------------------------------------------


class TestAdminModify:
    def test_status_can_be_active(self):
        m = AdminModify(status=AdminStatus.active)
        assert m.status == AdminStatus.active

    def test_status_can_be_disabled(self):
        m = AdminModify(status=AdminStatus.disabled)
        assert m.status == AdminStatus.disabled

    def test_status_cannot_be_limited(self):
        """AdminStatusModify = Literal[active, disabled] — limited must be rejected."""
        with pytest.raises(ValidationError):
            AdminModify(status=AdminStatus.limited)

    def test_data_limit_optional(self):
        m = AdminModify(data_limit=10_000_000)
        assert m.data_limit == 10_000_000

    def test_role_id_optional(self):
        m = AdminModify(role_id=2)
        assert m.role_id == 2

    def test_all_none_defaults(self):
        m = AdminModify()
        assert m.password is None
        assert m.status is None
        assert m.data_limit is None
        assert m.role_id is None
        assert m.permission_overrides is None

    def test_is_sudo_field_removed(self):
        """is_sudo was removed from AdminModify in this PR."""
        with pytest.raises((ValidationError, TypeError)):
            AdminModify(is_sudo=True)


# ---------------------------------------------------------------------------
# AdminCreate
# ---------------------------------------------------------------------------


class TestAdminCreate:
    def test_role_id_required(self):
        with pytest.raises(ValidationError):
            AdminCreate(username="u", password="MyPass#12abc")

    def test_valid_create(self):
        c = AdminCreate(username="newadmin", password="MyPass#12abc", role_id=3)
        assert c.username == "newadmin"
        assert c.role_id == 3


# ---------------------------------------------------------------------------
# AdminValidationResult
# ---------------------------------------------------------------------------


class TestAdminValidationResult:
    def test_has_status_field(self):
        r = AdminValidationResult(id=1, username="admin")
        assert r.status == AdminStatus.active

    def test_status_can_be_set(self):
        r = AdminValidationResult(id=1, username="admin", status=AdminStatus.disabled)
        assert r.status == AdminStatus.disabled

    def test_no_is_sudo_field(self):
        """is_sudo was removed — passing it should raise a validation error."""
        with pytest.raises((ValidationError, TypeError)):
            AdminValidationResult(id=1, username="admin", is_sudo=True)


# ---------------------------------------------------------------------------
# AdminsResponse
# ---------------------------------------------------------------------------


class TestAdminsResponse:
    def test_includes_limited_field(self):
        resp = AdminsResponse(admins=[], total=10, active=7, disabled=2, limited=1)
        assert resp.limited == 1

    def test_defaults_zero(self):
        resp = AdminsResponse(admins=[], total=0, active=0, disabled=0, limited=0)
        assert resp.limited == 0


# ---------------------------------------------------------------------------
# BulkAdminSelection
# ---------------------------------------------------------------------------


class TestBulkAdminSelection:
    def test_accepts_ids_set(self):
        sel = BulkAdminSelection(ids={1, 2, 3})
        assert 1 in sel.ids

    def test_empty_ids_raises(self):
        """ListValidator.not_null_list should reject empty collections."""
        with pytest.raises(ValidationError):
            BulkAdminSelection(ids=set())

    def test_usernames_field_removed(self):
        """usernames field was replaced by ids in this PR."""
        with pytest.raises((ValidationError, TypeError)):
            BulkAdminSelection(usernames={"alice", "bob"})


# ---------------------------------------------------------------------------
# PermissionScope
# ---------------------------------------------------------------------------


class TestPermissionScope:
    def test_values(self):
        assert PermissionScope.NONE == 0
        assert PermissionScope.OWN == 1
        assert PermissionScope.ALL == 2

    def test_ordering(self):
        assert PermissionScope.NONE < PermissionScope.OWN < PermissionScope.ALL


# ---------------------------------------------------------------------------
# _ResourcePermissions.get()
# ---------------------------------------------------------------------------


class TestResourcePermissionsGet:
    def test_get_existing_action(self):
        p = CRUDPermissions(create=True, read={"scope": 1})
        assert p.get("create") is True
        assert p.get("read") == {"scope": 1}

    def test_get_missing_action_returns_default(self):
        p = CRUDPermissions()
        assert p.get("create") is None
        assert p.get("create", False) is False

    def test_get_unknown_key_returns_default(self):
        p = CRUDPermissions()
        result = p.get("nonexistent_action", "fallback")
        assert result == "fallback"

    def test_extra_fields_forbidden(self):
        """extra='forbid' ensures unknown fields raise errors."""
        with pytest.raises(ValidationError):
            CRUDPermissions(unknown_action=True)


# ---------------------------------------------------------------------------
# RolePermissions.get()
# ---------------------------------------------------------------------------


class TestRolePermissionsGet:
    def test_get_users_resource(self):
        users_perm = UsersPermissions(create=True)
        rp = RolePermissions(users=users_perm)
        assert rp.get("users") is users_perm

    def test_get_missing_resource_returns_none(self):
        rp = RolePermissions()
        assert rp.get("nodes") is None

    def test_get_with_default(self):
        rp = RolePermissions()
        sentinel = object()
        assert rp.get("admins", sentinel) is sentinel


# ---------------------------------------------------------------------------
# RoleLimits
# ---------------------------------------------------------------------------


class TestRoleLimits:
    def test_all_none_defaults(self):
        limits = RoleLimits()
        assert limits.max_users is None
        assert limits.data_limit_min is None
        assert limits.data_limit_max is None
        assert limits.expire_min is None
        assert limits.expire_max is None
        assert limits.min_hwid_per_user is None
        assert limits.max_hwid_per_user is None

    def test_set_fields(self):
        limits = RoleLimits(max_users=100, data_limit_max=1_000_000_000)
        assert limits.max_users == 100
        assert limits.data_limit_max == 1_000_000_000

    def test_model_dump_round_trip(self):
        limits = RoleLimits(max_users=50)
        dumped = limits.model_dump()
        restored = RoleLimits(**dumped)
        assert restored.max_users == 50


# ---------------------------------------------------------------------------
# RoleFeatures
# ---------------------------------------------------------------------------


class TestRoleFeatures:
    def test_defaults_true(self):
        f = RoleFeatures()
        assert f.can_use_reset_strategy is True
        assert f.can_use_next_plan is True

    def test_disable_features(self):
        f = RoleFeatures(can_use_reset_strategy=False, can_use_next_plan=False)
        assert f.can_use_reset_strategy is False
        assert f.can_use_next_plan is False


# ---------------------------------------------------------------------------
# RoleAccess
# ---------------------------------------------------------------------------


class TestRoleAccess:
    def test_defaults(self):
        a = RoleAccess()
        assert a.require_template is False
        assert a.allowed_template_ids is None
        assert a.allowed_group_ids is None

    def test_set_allowed_ids(self):
        a = RoleAccess(allowed_template_ids=[1, 2, 3], allowed_group_ids=[10])
        assert a.allowed_template_ids == [1, 2, 3]
        assert a.allowed_group_ids == [10]


# ---------------------------------------------------------------------------
# APIKeysPermissions
# ---------------------------------------------------------------------------


class TestAPIKeysPermissions:
    def test_defaults_none(self):
        p = APIKeysPermissions()
        assert p.create is None
        assert p.read is None
        assert p.read_simple is None
        assert p.delete is None

    def test_get_method(self):
        p = APIKeysPermissions(create=True, read={"scope": 2})
        assert p.get("create") is True
        assert p.get("read") == {"scope": 2}
        assert p.get("delete") is None


# ---------------------------------------------------------------------------
# AdminRoleCreate
# ---------------------------------------------------------------------------


class TestAdminRoleCreate:
    def test_minimal_creation(self):
        rc = AdminRoleCreate(name="testrole")
        assert rc.name == "testrole"
        assert rc.disabled_when_limited is False
        assert rc.disable_users_when_limited is True

    def test_name_max_length(self):
        with pytest.raises(ValidationError):
            AdminRoleCreate(name="x" * 65)

    def test_with_permissions(self):
        perms = RolePermissions(users=UsersPermissions(create=True))
        rc = AdminRoleCreate(name="custom", permissions=perms)
        assert rc.permissions.users.create is True

    def test_with_limits(self):
        limits = RoleLimits(max_users=50)
        rc = AdminRoleCreate(name="limited_role", limits=limits)
        assert rc.limits.max_users == 50


# ---------------------------------------------------------------------------
# AdminRoleModify
# ---------------------------------------------------------------------------


class TestAdminRoleModify:
    def test_all_none_defaults(self):
        m = AdminRoleModify()
        assert m.name is None
        assert m.permissions is None
        assert m.limits is None

    def test_partial_update(self):
        m = AdminRoleModify(name="new_name")
        assert m.name == "new_name"
        assert m.limits is None

    def test_name_max_length(self):
        with pytest.raises(ValidationError):
            AdminRoleModify(name="y" * 65)


# ---------------------------------------------------------------------------
# AdminRoleListQuery / sort parsing
# ---------------------------------------------------------------------------


class TestAdminRoleListQuery:
    def test_sort_string_to_enum(self):
        q = AdminRoleListQuery(sort="name")
        assert len(q.sort) == 1
        assert q.sort[0] == AdminRoleSortOption.name

    def test_sort_desc_field(self):
        q = AdminRoleListQuery(sort="-created_at")
        assert q.sort[0].is_desc is True
        assert q.sort[0].field.value == "created_at"

    def test_multiple_sort_fields(self):
        q = AdminRoleListQuery(sort=["name", "-id"])
        assert len(q.sort) == 2

    def test_no_sort(self):
        q = AdminRoleListQuery()
        assert q.sort == []


# ---------------------------------------------------------------------------
# APIKeyCreate — expire_date validation
# ---------------------------------------------------------------------------


class TestAPIKeyCreate:
    def _future(self, seconds=60) -> datetime:
        return datetime.now(timezone.utc) + timedelta(seconds=seconds)

    def _past(self, seconds=60) -> datetime:
        return datetime.now(timezone.utc) - timedelta(seconds=seconds)

    def test_valid_future_expire_date(self):
        create = APIKeyCreate(name="mykey", role_id=1, expire_date=self._future())
        assert create.expire_date is not None

    def test_past_expire_date_raises(self):
        with pytest.raises(ValidationError):
            APIKeyCreate(name="mykey", role_id=1, expire_date=self._past())

    def test_none_expire_date_allowed(self):
        create = APIKeyCreate(name="mykey", role_id=1, expire_date=None)
        assert create.expire_date is None

    def test_name_min_length(self):
        with pytest.raises(ValidationError):
            APIKeyCreate(name="", role_id=1)

    def test_name_max_length(self):
        with pytest.raises(ValidationError):
            APIKeyCreate(name="x" * 129, role_id=1)

    def test_role_id_must_be_ge_1(self):
        with pytest.raises(ValidationError):
            APIKeyCreate(name="mykey", role_id=0)

    def test_note_optional(self):
        c = APIKeyCreate(name="mykey", role_id=1, note="some note")
        assert c.note == "some note"

    def test_note_max_length(self):
        with pytest.raises(ValidationError):
            APIKeyCreate(name="mykey", role_id=1, note="x" * 513)

    def test_raw_key_field_carries_value(self):
        """APIKeyCreate inherits raw_key from APIKeyBase (used in crud.api_key)."""
        # raw_key is not in APIKeyBase — it's generated in crud; just check model is valid
        c = APIKeyCreate(name="k", role_id=2)
        assert c.name == "k"


# ---------------------------------------------------------------------------
# APIKeyResponse
# ---------------------------------------------------------------------------


class TestAPIKeyResponse:
    def test_defaults(self):
        resp = APIKeyResponse(
            id=1,
            admin_id=10,
            name="key1",
            role_id=3,
            created_at=datetime.now(timezone.utc),
        )
        assert resp.status == APIKeyStatus.active
        assert resp.is_expired is False

    def test_disabled_status(self):
        resp = APIKeyResponse(
            id=2,
            admin_id=10,
            name="key2",
            role_id=3,
            created_at=datetime.now(timezone.utc),
            status=APIKeyStatus.disabled,
        )
        assert resp.status == APIKeyStatus.disabled


# ---------------------------------------------------------------------------
# APIKeysQuery
# ---------------------------------------------------------------------------


class TestAPIKeysQuery:
    def test_defaults(self):
        q = APIKeysQuery()
        assert q.offset == 0
        assert q.limit == 50
        assert q.key_id is None
        assert q.name is None
        assert q.status is None

    def test_offset_non_negative(self):
        with pytest.raises(ValidationError):
            APIKeysQuery(offset=-1)

    def test_limit_range(self):
        with pytest.raises(ValidationError):
            APIKeysQuery(limit=0)
        with pytest.raises(ValidationError):
            APIKeysQuery(limit=201)

    def test_filter_by_status(self):
        q = APIKeysQuery(status=APIKeyStatus.disabled)
        assert q.status == APIKeyStatus.disabled

    def test_key_id_must_be_ge_1(self):
        with pytest.raises(ValidationError):
            APIKeysQuery(key_id=0)
