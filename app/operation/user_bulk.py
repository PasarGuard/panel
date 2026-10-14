import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from sqlalchemy import select

from app import notification
from app.db import AsyncSession
from app.db.base import begin_immediate_if_sqlite
from app.db.crud.admin import get_admin
from app.db.crud.user import filter_users_stmt, get_users, modify_user
from app.db.models import User, UserStatus
from app.models.admin import AdminDetails
from app.models.proxy import ProxyTable
from app.models.user import UserListQuery, UserModify
from app.models.user_bulk import BulkUserEditSample, BulkUsersEdit, BulkUsersEditResult
from app.node.sync import _loaded_admin_sync_blocked, remove_users as sync_remove_users, sync_users
from app.node.user import node_payload_signature
from app.operation.permissions import PermissionDenied, enforce_permission, get_scope_admin_id, is_scope_all
from app.operation.user import UserOperation, logger
from app.utils.helpers import fix_datetime_timezone

_BATCH_SIZE = 500
_SAMPLE_SIZE = 10
_STATE_FIELDS = (
    "data_limit",
    "expire",
    "data_limit_reset_strategy",
    "hwid_limit",
    "status",
    "note",
    "on_hold_expire_duration",
    "on_hold_timeout",
    "auto_delete_in_days",
)


def _state(user: User) -> dict:
    """Snapshot editable account state without exposing proxy credentials."""
    values = {field: getattr(user, field) for field in _STATE_FIELDS}
    for field, value in values.items():
        if isinstance(value, datetime):
            values[field] = fix_datetime_timezone(value)
    values["group_ids"] = sorted(group.id for group in user.groups)
    values["owner"] = user.admin.username
    values["next_plan"] = (
        {
            field: getattr(user.next_plan, field)
            for field in ("user_template_id", "data_limit", "expire", "add_remaining_traffic")
        }
        if user.next_plan
        else None
    )
    values["shadowsocks_method"] = user.proxy_settings.get("shadowsocks", {}).get("method")
    return jsonable_encoder(values)


def _build_patch(user: User, body: BulkUsersEdit) -> tuple[UserModify, dict, bool]:
    """Build a validated partial update and its preview, preserving omitted fields."""
    before = _state(user)
    values = body.settings.model_dump(exclude_unset=True)
    skipped = False
    if "note" in values and values["note"] is None:
        values["note"] = ""
    if "on_hold_timeout" in values and values["on_hold_timeout"] is None:
        values["on_hold_timeout"] = 0
    if body.data_limit:
        edit = body.data_limit
        if edit.operation in {"set", "clear"}:
            values["data_limit"] = edit.value if edit.operation == "set" else 0
        elif not user.data_limit:
            skipped = True  # Relative arithmetic never converts an unlimited account to a finite one.
        else:
            value = user.data_limit + edit.value * (1 if edit.operation == "add" else -1)
            if value <= 0 or value > 9_223_372_036_854_775_807:
                raise ValueError("Relative traffic must leave a positive limit; use Clear for unlimited")
            values["data_limit"] = value
    if body.expire:
        edit = body.expire
        effective_status = values.get("status", user.status)
        if edit.operation in {"set", "clear"}:
            if effective_status == UserStatus.on_hold:
                raise ValueError("Set an active or disabled status to change an on-hold user's expiration date")
            values["expire"] = edit.value if edit.operation == "set" else 0
        elif (user.status == UserStatus.on_hold) != (effective_status == UserStatus.on_hold):
            raise ValueError(
                "Relative expiration cannot accompany a change into or out of on-hold status. "
                "Set an expiration date or on-hold duration instead."
            )
        elif effective_status == UserStatus.on_hold:
            duration = values.get("on_hold_expire_duration", user.on_hold_expire_duration)
            if not duration:
                raise ValueError("On-hold user has no expiration duration")
            values["on_hold_expire_duration"] = duration + edit.seconds * (1 if edit.operation == "add" else -1)
            if values["on_hold_expire_duration"] <= 0:
                raise ValueError("Relative expiration must leave a positive on-hold duration")
        elif user.expire:
            values["expire"] = fix_datetime_timezone(user.expire) + timedelta(
                seconds=edit.seconds * (1 if edit.operation == "add" else -1)
            )
        else:
            skipped = True
    if body.groups:
        edit = body.groups
        current = set(before["group_ids"])
        values["group_ids"] = sorted(
            set(edit.ids)
            if edit.operation == "set"
            else (current | set(edit.ids)) - set(edit.remove_ids)
            if edit.operation == "add"
            else current - set(edit.ids)
            if edit.operation == "remove"
            else set()
        )
    if values.get("status") == UserStatus.on_hold:
        values.setdefault("on_hold_expire_duration", user.on_hold_expire_duration)
    if body.shadowsocks_method:
        proxy = ProxyTable.model_validate(user.proxy_settings)
        proxy.shadowsocks.method = body.shadowsocks_method
        values["proxy_settings"] = proxy
    patch = UserModify(**values)
    after = dict(before)
    for field in _STATE_FIELDS:
        if field in values:
            value = getattr(patch, field)
            after[field] = jsonable_encoder(value)
    if "data_limit" in values:
        after["data_limit"] = patch.data_limit or None
    if "expire" in values:
        after["expire"] = jsonable_encoder(patch.expire) if patch.expire else None
    if "note" in values:
        after["note"] = patch.note or None
    if "group_ids" in values:
        after["group_ids"] = values["group_ids"]
    if "on_hold_timeout" in values:
        after["on_hold_timeout"] = jsonable_encoder(patch.on_hold_timeout) if patch.on_hold_timeout else None
    if "next_plan" in values:
        after["next_plan"] = jsonable_encoder(patch.next_plan) if patch.next_plan else None
    if body.owner:
        after["owner"] = body.owner
    if body.shadowsocks_method:
        after["shadowsocks_method"] = body.shadowsocks_method
    if patch.status == UserStatus.on_hold:
        after["expire"] = None
    # Derive status from the final limits, including both limits changing together.
    status_fields = {"status", "expire", "data_limit", "on_hold_expire_duration"}
    if status_fields & values.keys() and after["status"] != UserStatus.disabled:
        if after["status"] == UserStatus.on_hold and not after["expire"]:
            if not after["on_hold_expire_duration"]:
                raise ValueError("On-hold users require a positive expiration duration")
            if after["data_limit"] and user.used_traffic >= after["data_limit"]:
                after["status"] = UserStatus.limited
        elif after["expire"] and fix_datetime_timezone(datetime.fromisoformat(after["expire"])) <= datetime.now(UTC):
            after["status"] = UserStatus.expired
        elif after["data_limit"] and user.used_traffic >= after["data_limit"]:
            after["status"] = UserStatus.limited
        elif (
            user.status == UserStatus.disabled
            and patch.status == UserStatus.active
            and after["on_hold_expire_duration"]
            and not after["expire"]
        ):
            after["status"] = UserStatus.on_hold
        else:
            after["status"] = UserStatus.active
    return patch, after, skipped


class _BulkValidationOperation(UserOperation):
    async def raise_error(self, message: str, code: int, db: AsyncSession | None = None):
        """Report validation failures without expiring users or releasing row locks."""
        # Validation makes no writes. Rolling back here would expire other loaded
        # users and release the locks needed to validate the entire selection.
        raise HTTPException(status_code=code, detail=str(message))


class BulkUserEditOperation(UserOperation):
    async def edit(self, db: AsyncSession, body: BulkUsersEdit, admin: AdminDetails, *, apply: bool = False):
        """Preview scoped edits or atomically commit an unchanged, validated preview."""
        try:
            enforce_permission(admin, "users", "update")
            if body.owner:
                enforce_permission(admin, "users", "set_owner")
        except PermissionDenied as exc:
            await self.raise_error(str(exc), 403)
        await self._enforce_manual_user_write_access(admin, db)
        if apply and body.preview_revision is None:
            await self.raise_error("Preview changes before applying", 400)
        if apply:
            await begin_immediate_if_sqlite(db)

        new_owner = None
        if body.owner:
            if not is_scope_all(admin, "users", "set_owner"):
                await self.raise_error("All-user owner permission is required", 403)
            new_owner = await get_admin(db, body.owner, load_users=False, load_usage_logs=False)
            if new_owner is None:
                await self.raise_error("Admin not found", 404)

        selection = body.selection
        query = selection.filters or UserListQuery(ids=selection.ids)
        stmt = filter_users_stmt(db, select(User.id), query)
        scope_id = get_scope_admin_id(admin, "users", "update")
        if scope_id is not None:
            stmt = stmt.where(User.admin_id == scope_id)
        if selection.filters is not None and query.ids:
            requested = filter_users_stmt(db, select(User.id), UserListQuery(ids=query.ids))
            if scope_id is not None:
                requested = requested.where(User.admin_id == scope_id)
            accessible_ids = set((await db.scalars(requested)).all())
            if accessible_ids != set(query.ids):
                await self.raise_error("One or more filtered user IDs were not found or are outside your access", 404)
        ids = list((await db.scalars(stmt.order_by(User.id))).all())
        if selection.ids is not None and set(ids) != set(selection.ids):
            await self.raise_error("One or more selected users were not found or are outside your access", 404)
        if not ids:
            await self.raise_error("No users match this selection", 400)

        if apply:
            # Lock in ID order before loading mutable state. All writes commit together.
            for offset in range(0, len(ids), _BATCH_SIZE):
                locked = list(
                    (
                        await db.scalars(
                            select(User.id)
                            .where(User.id.in_(ids[offset : offset + _BATCH_SIZE]))
                            .order_by(User.id)
                            .with_for_update()
                        )
                    ).all()
                )
                if len(locked) != len(ids[offset : offset + _BATCH_SIZE]):
                    await self.raise_error("Selection changed; preview again", 409, db=db)

        digest = hashlib.sha256(body.model_dump_json(exclude={"preview_revision"}).encode())
        prepared = []
        before_signatures = {}
        validator = _BulkValidationOperation(self.operator_type)
        samples = []
        errors = []
        error_count = 0
        skipped_count = 0
        for offset in range(0, len(ids), _BATCH_SIZE):
            users = await get_users(
                db,
                UserListQuery(ids=ids[offset : offset + _BATCH_SIZE]),
                load_admin_role=True,
                load_usage_logs=False,
                load_group_inbounds=True,
                load_lifetime_used_traffic=True,
            )
            if len(users) != len(ids[offset : offset + _BATCH_SIZE]):
                await self.raise_error("Selection changed; preview again", 409, db=db)
            for user in sorted(users, key=lambda item: item.id):
                if scope_id is not None and user.admin_id != scope_id:
                    await self.raise_error("Selection changed; preview again", 409, db=db)
                before = _state(user)
                digest.update(
                    json.dumps(
                        [user.id, before, jsonable_encoder(user.edit_at)], sort_keys=True, separators=(",", ":")
                    ).encode()
                )
                try:
                    patch, after, skipped = _build_patch(user, body)
                    groups = await validator._prepare_modified_user(
                        db,
                        user,
                        patch,
                        admin,
                        prepare_proxy_settings=body.groups is not None or body.shadowsocks_method is not None,
                    )
                    # A null expiry must also obey role limits (ordinary partial updates omit it).
                    if body.expire and body.expire.operation == "clear":
                        await validator._enforce_user_limits(
                            db,
                            admin,
                            expire=0,
                            status=after["status"],
                            require_finite_expire=True,
                            require_finite_data_limit=False,
                            require_finite_on_hold_timeout=False,
                            require_finite_hwid_limit=False,
                        )
                    digest.update(json.dumps(after, sort_keys=True, separators=(",", ":")).encode())
                    changes = {
                        key: {"before": before[key], "after": value}
                        for key, value in after.items()
                        if before[key] != value
                    }
                    skipped_count += int(skipped)
                    if changes:
                        if apply:
                            before_signatures[user.id] = await node_payload_signature(user)
                        prepared.append((user, patch, groups, after, user.status))
                        if len(samples) < _SAMPLE_SIZE:
                            samples.append(BulkUserEditSample(id=user.id, username=user.username, changes=changes))
                except (HTTPException, ValidationError, ValueError, OverflowError) as exc:
                    error_count += 1
                    if len(errors) < 20:
                        detail = str(exc.detail) if isinstance(exc, HTTPException) else str(exc)
                        errors.append({"id": user.id, "username": user.username, "detail": detail})

        revision = digest.hexdigest()
        result = BulkUsersEditResult(
            affected_users=len(ids),
            changed_users=len(prepared),
            unchanged_users=len(ids) - len(prepared) - error_count,
            relative_skipped_users=skipped_count,
            error_count=error_count,
            errors=errors,
            samples=samples,
            revision=revision,
        )
        if not apply:
            return result
        if revision != body.preview_revision:
            await self.raise_error("Users or changes differ from the preview; preview again", 409, db=db)
        if error_count:
            await db.rollback()
            raise HTTPException(status_code=400, detail=result.model_dump(mode="json"))

        try:
            for user, patch, groups, after, old_status in prepared:
                self._apply_explicit_null_hwid_limit(user, patch)
                await modify_user(db, user, patch, groups=groups, commit=False)
                for field in ("on_hold_expire_duration", "auto_delete_in_days"):
                    if field in body.settings.model_fields_set:
                        setattr(user, field, getattr(patch, field))
                user.status = UserStatus(after["status"])
                if user.status != old_status:
                    user.last_status_change = datetime.now(UTC)
                if new_owner is not None:
                    user.admin = new_owner
            await db.commit()
        except ValueError as exc:
            await db.rollback()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception:
            await db.rollback()
            raise

        result.applied = True
        for offset in range(0, len(prepared), _BATCH_SIZE):
            batch = await get_users(
                db,
                UserListQuery(ids=[item[0].id for item in prepared[offset : offset + _BATCH_SIZE]]),
                load_admin_role=True,
                load_usage_logs=False,
                load_group_inbounds=True,
                load_lifetime_used_traffic=True,
            )
            try:
                removals = [user for user in batch if _loaded_admin_sync_blocked(user.admin)]
                removal_ids = {user.id for user in removals}
                updates = [
                    user
                    for user in batch
                    if user.id not in removal_ids and await node_payload_signature(user) != before_signatures[user.id]
                ]
                if removals:
                    await sync_remove_users(removals, await_dispatch=True)
                if updates:
                    await sync_users(updates, await_dispatch=True)
            except Exception:
                result.sync_pending = True
                logger.exception("Bulk user edit committed but node synchronization failed")
            old_statuses = {item[0].id: item[4] for item in prepared[offset : offset + _BATCH_SIZE]}
            for user in batch:
                response = await self.validate_user(user, include_subscription_url=False)
                asyncio.create_task(notification.modify_user(response, admin))
                if user.status != old_statuses[user.id]:
                    asyncio.create_task(notification.user_status_change(response, admin))
                logger.info('User "%s" (id %s) bulk edited by admin "%s"', user.username, user.id, admin.username)
        return result
