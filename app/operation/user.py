import asyncio
import re
import secrets
import warnings
from collections import Counter
from datetime import datetime, datetime as dt, timedelta as td, timezone, timezone as tz

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app import notification
from app.db import AsyncSession
from app.db.crud.admin import get_admin
from app.db.crud.bulk import (
    count_bulk_datalimit_targets,
    count_bulk_expire_targets,
    count_bulk_proxy_targets,
    get_bulk_wireguard_peer_ip_users,
    reset_all_users_data_usage,
    update_users_datalimit,
    update_users_expire,
    update_users_proxy_settings,
)
from app.db.crud.hwid import get_user_hwid_count
from app.db.crud.user import (
    build_revoked_proxy_settings,
    bulk_reset_user_data_usage,
    bulk_revoke_user_sub,
    bulk_set_owner,
    create_user,
    create_users_bulk,
    get_all_users_usages,
    get_existing_usernames,
    get_expired_users,
    get_user_count_metric_stats,
    get_user_usages,
    get_users,
    get_users_by_ids,
    get_users_by_usernames,
    get_users_count_by_admin,
    get_users_simple,
    get_users_sub_update_list,
    get_users_subscription_agent_counts,
    load_user_attrs,
    lock_admin_quota_row,
    modify_user as crud_modify_user,
    remove_expired_users,
    remove_user,
    remove_users,
    reset_user_by_next,
    reset_user_data_usage,
    revoke_user_sub,
    set_owner,
)
from app.db.models import User, UserStatus, UserTemplate
from app.models.admin import AdminDetails
from app.models.proxy import ProxyTable
from app.models.stats import (
    Period,
    UserCountMetric,
    UserCountMetricStatsList,
    UserUsageStatsList,
    validate_user_count_metric_scope,
)
from app.models.user import (
    BulkOperationDryRunResponse,
    BulkUser,
    BulkUsersActionResponse,
    BulkUsersApplyTemplate,
    BulkUsersCreateResponse,
    BulkUsersFromTemplate,
    BulkUsersProxy,
    BulkUsersSelection,
    BulkUsersSetOwner,
    BulkWireGuardPeerIPs,
    CreateUserFromTemplate,
    ExpiredUsersQuery,
    ModifyUserByTemplate,
    RemoveUsersResponse,
    UserCreate,
    UserListQuery,
    UserModify,
    UsernameGenerationStrategy,
    UserNotificationResponse,
    UserResponse,
    UserStatusToggle,
    UserSimple,
    UserSimpleListQuery,
    UsersResponse,
    UsersSimpleResponse,
    UserSubscriptionUpdateChart,
    UserSubscriptionUpdateChartSegment,
    UserSubscriptionUpdateList,
    UsersUsageQuery,
    UserUsageQuery,
    WireGuardPeerIPsReallocateResponse,
)
from app.node.sync import remove_user as sync_remove_user, sync_user, sync_users
from app.operation import BaseOperation, OperatorType
from app.operation.permissions import (
    PermissionDenied,
    apply_template_access,
    enforce_permission,
    get_effective_limits,
    get_scope_admin_id,
    is_scope_all,
)
from app.settings import hwid_settings, subscription_settings
from app.utils.helpers import fix_datetime_timezone
from app.utils.hwid import resolve_effective_hwid_settings
from app.utils.jwt import create_subscription_token
from app.utils.logger import get_logger
from app.utils.system import readable_duration, readable_size
from app.utils.wireguard import (
    build_wireguard_peer_ip_allocator,
    bulk_reallocate_wireguard_peer_ips as run_bulk_reallocate_wireguard_peer_ips,
    ensure_unique_wireguard_public_key,
    get_wireguard_tags_from_groups,
    prepare_wireguard_keys_only,
    prepare_wireguard_proxy_settings,
    prepare_wireguard_proxy_settings_with_allocator,
)
from config import subscription_env_settings, usage_settings, wireguard_settings


def _has_permission(admin: AdminDetails, resource: str, action: str) -> bool:
    """Return True if admin has the given resource+action permission (no scope check)."""
    try:
        enforce_permission(admin, resource, action)
        return True
    except PermissionDenied:
        return False


logger = get_logger("user-operation")

_USER_AGENT_SPLIT_RE = re.compile(r"[;/\s\(\)]+")
_VERSION_TOKEN_RE = re.compile(r"v?\d+(?:\.\d+)*", re.IGNORECASE)


def _duplicate_wireguard_public_key_usernames(users: list[UserCreate]) -> tuple[str, list[str]] | None:
    owners: dict[str, list[str]] = {}
    for user in users:
        public_key = user.proxy_settings.wireguard.public_key
        if public_key:
            owners.setdefault(public_key, []).append(user.username)
    for public_key, usernames in owners.items():
        if len(usernames) > 1:
            return public_key, usernames
    return None


def _resolve_enabled_user_status(user: User) -> UserStatus:
    now = dt.now(tz.utc)
    expire = user.expire
    if expire is not None and expire.replace(tzinfo=tz.utc) <= now:
        return UserStatus.expired
    if user.data_limit is not None and user.data_limit > 0 and user.used_traffic >= user.data_limit:
        return UserStatus.limited
    if user.on_hold_expire_duration is not None:
        return UserStatus.on_hold
    return UserStatus.active


class UserOperation(BaseOperation):
    @staticmethod
    def _is_non_blocking_sync_operator(operator_type: OperatorType) -> bool:
        return operator_type in (OperatorType.API, OperatorType.WEB)

    @staticmethod
    def _format_validation_errors(error: ValidationError) -> str:
        return "; ".join(
            [f"{'.'.join(str(loc_part) for loc_part in err['loc'])}: {err['msg']}" for err in error.errors()]
        )

    @staticmethod
    async def generate_subscription_url(user: UserNotificationResponse):
        salt = secrets.token_hex(8)
        settings = await subscription_settings()
        url_prefix = (
            user.admin.sub_domain.replace("*", salt)
            if user.admin and user.admin.sub_domain
            else (settings.url_prefix).replace("*", salt)
        )
        token = await create_subscription_token(user.id)
        return f"{url_prefix}/{subscription_env_settings.path}/{token}"

    async def _generate_usernames(
        self,
        base_username: str | None,
        count: int,
        strategy: UsernameGenerationStrategy,
        start_number: int | None = None,
        username_prefix: str | None = None,
        username_suffix: str | None = None,
    ) -> list[str]:
        def _apply_affixes(candidate: str) -> str:
            return (
                f"{username_prefix if username_prefix else ''}{candidate}{username_suffix if username_suffix else ''}"
            )

        if count <= 0:
            await self.raise_error(message="count must be greater than zero", code=400)
        if start_number is not None and start_number < 0:
            await self.raise_error(message="start_number must be zero or greater", code=400)

        if strategy == UsernameGenerationStrategy.random:
            if base_username not in (None, ""):
                await self.raise_error(message="username must be null when strategy is 'random'", code=400)
            if start_number is not None:
                await self.raise_error(message="start_number is only supported for sequence strategy", code=400)

            generated: list[str] = []
            seen: set[str] = set()
            max_attempts = max(100, count * 20)
            attempts = 0
            while len(generated) < count:
                attempts += 1
                if attempts > max_attempts:
                    await self.raise_error(message="unable to generate unique usernames", code=500)
                candidate = _apply_affixes(secrets.token_hex(6))
                if candidate in seen:
                    continue
                seen.add(candidate)
                generated.append(candidate)
            return generated

        if strategy == UsernameGenerationStrategy.sequence:
            if not base_username:
                await self.raise_error(message="base username is required for sequence strategy", code=400)

            sequence_base_username = _apply_affixes(base_username)

            if not (3 <= len(sequence_base_username) <= 128):
                await self.raise_error(
                    message="base username with affixes must be between 3 and 128 characters", code=400
                )

            width = 0
            inferred_start_number = 1

            generated: list[str] = []
            current = start_number if start_number is not None else inferred_start_number
            for _ in range(count):
                suffix = str(current)
                if width:
                    suffix = suffix.zfill(width)
                generated.append(f"{sequence_base_username}{suffix}")
                current += 1
            return generated

        await self.raise_error(message="unsupported username generation strategy", code=400)

    def _build_bulk_user_models(self, candidate_usernames: list[str], builder):
        users: list[UserCreate] = []
        seen: set[str] = set()

        for username in candidate_usernames:
            if username in seen:
                continue
            seen.add(username)

            try:
                user_model = builder(username)
            except HTTPException:
                continue
            except ValidationError:
                continue

            if user_model is not None:
                users.append(user_model)

        return users

    async def _filter_existing_usernames(self, db: AsyncSession, new_users: list[UserCreate]) -> list[UserCreate]:
        if not new_users:
            return []

        existing_usernames = await get_existing_usernames(db, [user.username for user in new_users])
        if not existing_usernames:
            return new_users

        return [user for user in new_users if user.username not in existing_usernames]

    async def _enforce_bulk_create_quota(
        self, db: AsyncSession, admin: AdminDetails, users_to_create_count: int
    ) -> None:
        if admin.is_owner or users_to_create_count <= 0:
            return

        limits = get_effective_limits(admin)
        if limits.max_users is None:
            return

        await lock_admin_quota_row(db, admin.id)
        current_count = await get_users_count_by_admin(db, admin.id)
        if current_count + users_to_create_count > limits.max_users:
            await self.raise_error(message=f"Bulk create would exceed user limit ({limits.max_users})", code=400, db=db)

    async def _persist_bulk_users(
        self,
        db: AsyncSession,
        admin: AdminDetails,
        db_admin,
        users_to_create: list[UserCreate],
        groups: list,
        *,
        skip_per_user_limits: bool = False,
        commit: bool = True,
        sync: bool = True,
    ) -> list[str]:
        if not users_to_create:
            return []

        existing_usernames = await get_existing_usernames(db, [user.username for user in users_to_create])
        if existing_usernames:
            await self.raise_error(message="User already exists", code=409, db=db)

        await self._enforce_bulk_create_quota(db, admin, len(users_to_create))

        if not skip_per_user_limits:
            for user_to_create in users_to_create:
                await self._enforce_user_limits(
                    db,
                    admin,
                    data_limit=user_to_create.data_limit,
                    expire=user_to_create.expire,
                    status=user_to_create.status,
                    on_hold_expire_duration=user_to_create.on_hold_expire_duration,
                    on_hold_timeout=user_to_create.on_hold_timeout,
                    hwid_limit=user_to_create.hwid_limit,
                    data_limit_reset_strategy=user_to_create.data_limit_reset_strategy,
                    next_plan=user_to_create.next_plan,
                )

        wireguard_tags = await get_wireguard_tags_from_groups(groups)
        use_shared_allocator = bool(wireguard_tags) and wireguard_settings.enabled

        if use_shared_allocator:
            allocator = await build_wireguard_peer_ip_allocator(db)
            for user_to_create in users_to_create:
                try:
                    user_to_create.proxy_settings = prepare_wireguard_proxy_settings_with_allocator(
                        user_to_create.proxy_settings,
                        allocator,
                    )
                except ValueError as exc:
                    await self.raise_error(message=str(exc), code=400, db=db)
        else:
            for user_to_create in users_to_create:
                user_to_create.proxy_settings = await self._prepare_user_proxy_settings(
                    db,
                    groups,
                    user_to_create.proxy_settings,
                )

        duplicate_key = _duplicate_wireguard_public_key_usernames(users_to_create)
        if duplicate_key is not None:
            public_key, usernames = duplicate_key
            await self.raise_error(
                message=(
                    f"wireguard public_key {public_key} is assigned to multiple new users: {', '.join(usernames[:2])}"
                ),
                code=400,
                db=db,
            )
        for user_to_create in users_to_create:
            try:
                await ensure_unique_wireguard_public_key(db, user_to_create.proxy_settings)
            except ValueError as exc:
                await self.raise_error(message=str(exc), code=400, db=db)

        db_users = await create_users_bulk(db, users_to_create, groups, db_admin, commit=commit)
        if not commit:
            for user in db_users:
                await load_user_attrs(user, load_admin_role=True)
        if sync:
            await sync_users(db_users)

        users_list = []
        for db_user in db_users:
            users_list.append(await self.validate_user(db_user))

        return [user.subscription_url for user in users_list]

    async def validate_user(self, db_user: User, include_subscription_url: bool = True) -> UserNotificationResponse:
        user = UserNotificationResponse.model_validate(db_user)
        if include_subscription_url:
            user.subscription_url = await self.generate_subscription_url(user)
        return user

    async def update_user(self, db_user: User, include_subscription_url: bool = True) -> UserNotificationResponse:
        await sync_user(db_user)

        user = await self.validate_user(
            db_user,
            include_subscription_url=include_subscription_url,
        )
        return user

    async def _prepare_user_proxy_settings(
        self,
        db: AsyncSession,
        groups: list,
        proxy_settings: ProxyTable,
        *,
        exclude_user_id: int | None = None,
        skip_peer_ip_validation: bool = False,
    ) -> ProxyTable:
        try:
            if skip_peer_ip_validation:
                return await prepare_wireguard_keys_only(
                    db,
                    proxy_settings,
                    groups,
                    exclude_user_id=exclude_user_id,
                )
            else:
                return await prepare_wireguard_proxy_settings(
                    db,
                    proxy_settings,
                    groups,
                    exclude_user_id=exclude_user_id,
                )
        except ValueError as exc:
            await self.raise_error(message=str(exc), code=400, db=db)

    async def _prepare_revoked_proxy_settings(self, db: AsyncSession, db_user: User) -> ProxyTable:
        groups = db_user.__dict__.get("groups")
        if groups is None:
            groups = await db_user.awaitable_attrs.groups

        return await self._prepare_user_proxy_settings(
            db,
            groups,
            ProxyTable.model_validate(build_revoked_proxy_settings(db_user)),
            exclude_user_id=db_user.id,
            skip_peer_ip_validation=True,
        )

    async def _get_validated_template_with_access(
        self, db: AsyncSession, template_id: int, admin: AdminDetails
    ) -> UserTemplate:
        """Fetch a user template and verify the admin is allowed to access it via allowed_template_ids."""
        allowed = apply_template_access(admin, [template_id])
        if allowed is not None and template_id not in allowed:
            await self.raise_error("User Template not found", 404)
        return await self.get_validated_user_template(db, template_id)

    async def _enforce_user_limits(
        self,
        db: AsyncSession,
        admin: AdminDetails,
        *,
        data_limit: int | None = None,
        expire: dt | int | None = None,
        status: UserStatus | None = None,
        on_hold_expire_duration: int | None = None,
        on_hold_timeout: dt | int | None = None,
        hwid_limit: int | None = None,
        data_limit_reset_strategy=None,
        next_plan=None,
        check_max_users: bool = False,
        require_finite_data_limit: bool = True,
        require_finite_expire: bool = True,
        require_finite_on_hold_timeout: bool = True,
        require_finite_hwid_limit: bool = True,
    ) -> None:
        """Enforce role-level limits and feature flags. No-op for owner."""
        if admin.is_owner:
            return

        limits = get_effective_limits(admin)

        if check_max_users and limits.max_users is not None:
            current_count = await get_users_count_by_admin(db, admin.id)
            if current_count >= limits.max_users:
                await self.raise_error(message=f"User limit reached ({limits.max_users})", code=400, db=db)

        if limits.data_limit_max is not None and require_finite_data_limit and (data_limit is None or data_limit <= 0):
            await self.raise_error(
                message=f"Data limit cannot be unlimited; maximum is {readable_size(limits.data_limit_max)}",
                code=400,
                db=db,
            )

        if data_limit is not None and data_limit > 0:
            if limits.data_limit_min is not None and data_limit < limits.data_limit_min:
                await self.raise_error(
                    message=f"Data limit must be at least {readable_size(limits.data_limit_min)}", code=400, db=db
                )
            if limits.data_limit_max is not None and data_limit > limits.data_limit_max:
                await self.raise_error(
                    message=f"Data limit cannot exceed {readable_size(limits.data_limit_max)}", code=400, db=db
                )

        status_value = getattr(status, "value", status)
        uses_on_hold_duration = status_value == UserStatus.on_hold.value

        if limits.expire_max is not None and require_finite_expire:
            if uses_on_hold_duration:
                if on_hold_expire_duration is None or on_hold_expire_duration <= 0:
                    await self.raise_error(
                        message=(
                            f"On-hold duration cannot be unlimited; maximum is {readable_duration(limits.expire_max)}"
                        ),
                        code=400,
                        db=db,
                    )
            elif expire is None or expire == 0:
                await self.raise_error(
                    message=f"Expire cannot be unlimited; maximum is {readable_duration(limits.expire_max)} from now",
                    code=400,
                    db=db,
                )

        if expire is not None and expire != 0:
            expire_dt = fix_datetime_timezone(expire)
            seconds = (expire_dt - datetime.now(timezone.utc)).total_seconds()
            if limits.expire_min is not None and seconds < limits.expire_min:
                await self.raise_error(
                    message=f"Expire must be at least {readable_duration(limits.expire_min)} from now",
                    code=400,
                    db=db,
                )
            if limits.expire_max is not None and seconds > limits.expire_max:
                await self.raise_error(
                    message=f"Expire cannot exceed {readable_duration(limits.expire_max)} from now",
                    code=400,
                    db=db,
                )

        if on_hold_expire_duration is not None and on_hold_expire_duration != 0:
            if limits.expire_min is not None and on_hold_expire_duration < limits.expire_min:
                await self.raise_error(
                    message=f"On-hold duration must be at least {readable_duration(limits.expire_min)}",
                    code=400,
                    db=db,
                )
            if limits.expire_max is not None and on_hold_expire_duration > limits.expire_max:
                await self.raise_error(
                    message=f"On-hold duration cannot exceed {readable_duration(limits.expire_max)}",
                    code=400,
                    db=db,
                )

        if (
            limits.on_hold_timeout_max is not None
            and require_finite_on_hold_timeout
            and (on_hold_timeout is None or on_hold_timeout == 0)
        ):
            await self.raise_error(
                message=f"On-hold timeout cannot be unlimited; maximum is {readable_duration(limits.on_hold_timeout_max)} from now",
                code=400,
                db=db,
            )

        if on_hold_timeout is not None and on_hold_timeout != 0:
            if isinstance(on_hold_timeout, dt):
                timeout_seconds = (fix_datetime_timezone(on_hold_timeout) - datetime.now(timezone.utc)).total_seconds()
            else:
                timeout_seconds = on_hold_timeout

            if limits.on_hold_timeout_min is not None and timeout_seconds < limits.on_hold_timeout_min:
                await self.raise_error(
                    message=f"On-hold timeout must be at least {readable_duration(limits.on_hold_timeout_min)}",
                    code=400,
                    db=db,
                )
            if limits.on_hold_timeout_max is not None and timeout_seconds > limits.on_hold_timeout_max:
                await self.raise_error(
                    message=f"On-hold timeout cannot exceed {readable_duration(limits.on_hold_timeout_max)}",
                    code=400,
                    db=db,
                )

        if (
            limits.max_hwid_per_user is not None
            and require_finite_hwid_limit
            and (hwid_limit is None or hwid_limit <= 0)
        ):
            await self.raise_error(
                message=f"HWID limit cannot be unlimited; maximum is {limits.max_hwid_per_user}",
                code=400,
                db=db,
            )

        if hwid_limit is not None:
            if limits.min_hwid_per_user is not None and hwid_limit < limits.min_hwid_per_user:
                await self.raise_error(
                    message=f"HWID limit must be at least {limits.min_hwid_per_user}", code=400, db=db
                )
            if limits.max_hwid_per_user is not None and hwid_limit > limits.max_hwid_per_user:
                await self.raise_error(message=f"HWID limit cannot exceed {limits.max_hwid_per_user}", code=400, db=db)

        features = admin.role.features if admin.role else None
        if features is not None:
            if data_limit_reset_strategy is not None and not features.can_use_reset_strategy:
                strategy_val = getattr(data_limit_reset_strategy, "value", str(data_limit_reset_strategy))
                if strategy_val != "no_reset":
                    await self.raise_error(message="Reset strategy is not allowed for your role", code=403, db=db)
            if next_plan is not None and not features.can_use_next_plan:
                await self.raise_error(message="Next plan is not allowed for your role", code=403, db=db)

    async def _enforce_manual_user_write_access(self, admin: AdminDetails, db: AsyncSession) -> None:
        if admin.is_owner or admin.role is None:
            return
        if admin.role.access.require_template:
            await self.raise_error(message="Manual user create/modify is not allowed for your role", code=403, db=db)

    async def create_user(
        self, db: AsyncSession, new_user: UserCreate, admin: AdminDetails, *, skip_role_limits: bool = False
    ) -> UserResponse:
        if not skip_role_limits:
            await self._enforce_manual_user_write_access(admin, db)

        global_hwid_conf = await hwid_settings()
        effective_hwid_conf = resolve_effective_hwid_settings(
            global_hwid_conf,
            admin.role.hwid if admin.role is not None else None,
        )

        if new_user.hwid_limit is None:
            new_user.hwid_limit = 0 if effective_hwid_conf is None else (effective_hwid_conf.fallback_limit or 0)

        if not skip_role_limits:
            await self._enforce_user_limits(
                db,
                admin,
                data_limit=new_user.data_limit,
                expire=new_user.expire,
                status=new_user.status,
                on_hold_expire_duration=new_user.on_hold_expire_duration,
                on_hold_timeout=new_user.on_hold_timeout,
                hwid_limit=new_user.hwid_limit,
                data_limit_reset_strategy=new_user.data_limit_reset_strategy,
                next_plan=new_user.next_plan,
                check_max_users=True,
            )

        if new_user.hwid_limit is not None and not admin.is_owner and effective_hwid_conf is not None:
            if effective_hwid_conf.min_limit is not None and new_user.hwid_limit < effective_hwid_conf.min_limit:
                await self.raise_error(
                    message=f"HWID limit cannot be less than {effective_hwid_conf.min_limit}", code=400, db=db
                )
            if (
                effective_hwid_conf.max_limit is not None
                and effective_hwid_conf.max_limit > 0
                and (new_user.hwid_limit > effective_hwid_conf.max_limit or new_user.hwid_limit == 0)
            ):
                await self.raise_error(
                    message=f"HWID limit cannot exceed {effective_hwid_conf.max_limit}", code=400, db=db
                )

        if new_user.next_plan is not None and new_user.next_plan.user_template_id is not None:
            await self.get_validated_user_template(db, new_user.next_plan.user_template_id)

        all_groups = await self.validate_all_groups(db, new_user)
        db_admin = await get_admin(db, admin.username, load_users=False, load_usage_logs=False)
        new_user.proxy_settings = await self._prepare_user_proxy_settings(db, all_groups, new_user.proxy_settings)

        try:
            db_user = await create_user(db, new_user, all_groups, db_admin)
        except IntegrityError:
            await self.raise_error(message="User already exists", code=409, db=db)

        user = await self.update_user(db_user)

        logger.info(f'New user "{db_user.username}" with id "{db_user.id}" added by admin "{admin.username}"')

        asyncio.create_task(notification.create_user(user, admin))

        return user

    async def _prepare_modified_user(
        self,
        db: AsyncSession,
        db_user: User,
        modified_user: UserModify,
        admin: AdminDetails,
        *,
        skip_role_limits: bool = False,
    ):
        if modified_user.hwid_limit is not None and modified_user.hwid_limit > 0:
            current_count = await get_user_hwid_count(db, db_user.id)
            if current_count > modified_user.hwid_limit:
                await self.raise_error(
                    message=f"Cannot lower HWID limit below current device count ({current_count}). Remove devices first.",
                    code=400,
                    db=db,
                )

        if not skip_role_limits:
            modified_fields = modified_user.model_fields_set
            data_limit_was_changed = "data_limit" in modified_fields and modified_user.data_limit is not None
            expire_was_changed = "expire" in modified_fields and modified_user.expire is not None
            status_was_changed = modified_user.status is not None
            modified_status_value = getattr(modified_user.status, "value", modified_user.status)
            status_requires_finite_expire = modified_status_value in {
                UserStatus.active.value,
                UserStatus.on_hold.value,
            }
            on_hold_duration_was_changed = (
                "on_hold_expire_duration" in modified_fields and modified_user.on_hold_expire_duration is not None
            )
            expire_requires_finite_limit = (
                expire_was_changed
                or (status_was_changed and status_requires_finite_expire)
                or on_hold_duration_was_changed
            )
            hwid_limit_was_changed = "hwid_limit" in modified_fields and modified_user.hwid_limit is not None
            on_hold_timeout_was_changed = "on_hold_timeout" in modified_fields
            on_hold_timeout_requires_finite_limit = on_hold_timeout_was_changed or (
                status_was_changed and modified_status_value == UserStatus.on_hold.value
            )

            effective_status = modified_user.status if modified_user.status is not None else db_user.status
            effective_expire = modified_user.expire
            effective_on_hold_expire_duration = modified_user.on_hold_expire_duration
            if status_was_changed and status_requires_finite_expire:
                if modified_status_value == UserStatus.on_hold.value:
                    effective_expire = None
                    if effective_on_hold_expire_duration is None:
                        effective_on_hold_expire_duration = db_user.on_hold_expire_duration
                elif effective_expire is None:
                    effective_expire = db_user.expire

            await self._enforce_user_limits(
                db,
                admin,
                data_limit=modified_user.data_limit,
                expire=effective_expire,
                status=effective_status,
                on_hold_expire_duration=effective_on_hold_expire_duration,
                on_hold_timeout=modified_user.on_hold_timeout,
                hwid_limit=modified_user.hwid_limit,
                data_limit_reset_strategy=modified_user.data_limit_reset_strategy,
                next_plan=modified_user.next_plan,
                require_finite_data_limit=data_limit_was_changed,
                require_finite_expire=expire_requires_finite_limit,
                require_finite_on_hold_timeout=on_hold_timeout_requires_finite_limit,
                require_finite_hwid_limit=hwid_limit_was_changed,
            )

        if modified_user.hwid_limit is not None and not admin.is_owner:
            global_hwid_conf = await hwid_settings()
            effective_hwid_conf = resolve_effective_hwid_settings(
                global_hwid_conf,
                admin.role.hwid if admin.role is not None else None,
            )
            if effective_hwid_conf is not None:
                if (
                    effective_hwid_conf.min_limit is not None
                    and modified_user.hwid_limit < effective_hwid_conf.min_limit
                ):
                    await self.raise_error(
                        message=f"HWID limit cannot be less than {effective_hwid_conf.min_limit}", code=400, db=db
                    )
                if (
                    effective_hwid_conf.max_limit is not None
                    and effective_hwid_conf.max_limit > 0
                    and (modified_user.hwid_limit > effective_hwid_conf.max_limit or modified_user.hwid_limit == 0)
                ):
                    await self.raise_error(
                        message=f"HWID limit cannot exceed {effective_hwid_conf.max_limit}", code=400, db=db
                    )

        validated_groups = None
        if modified_user.group_ids:
            validated_groups = await self.validate_all_groups(db, modified_user)

        if modified_user.next_plan is not None and modified_user.next_plan.user_template_id is not None:
            await self.get_validated_user_template(db, modified_user.next_plan.user_template_id)

        effective_groups = validated_groups if validated_groups is not None else db_user.groups
        current_proxy_settings = ProxyTable.model_validate(db_user.proxy_settings)
        current_proxy_settings_data = current_proxy_settings.dict()
        proxy_settings_to_prepare = (
            ProxyTable.model_validate(modified_user.proxy_settings.dict())
            if modified_user.proxy_settings is not None
            else ProxyTable.model_validate(current_proxy_settings_data)
        )

        old_peer_ips = set(current_proxy_settings.wireguard.peer_ips or [])
        new_peer_ips = set(proxy_settings_to_prepare.wireguard.peer_ips or [])
        peer_ips_changed = old_peer_ips != new_peer_ips

        prepared_proxy_settings = await self._prepare_user_proxy_settings(
            db,
            effective_groups,
            proxy_settings_to_prepare,
            exclude_user_id=db_user.id,
            skip_peer_ip_validation=not peer_ips_changed,
        )
        if modified_user.proxy_settings is not None or prepared_proxy_settings.dict() != current_proxy_settings_data:
            modified_user.proxy_settings = prepared_proxy_settings

        return validated_groups

    async def _apply_modified_user(
        self,
        db: AsyncSession,
        db_user: User,
        modified_user: UserModify,
        admin: AdminDetails,
        *,
        validated_groups=None,
    ) -> UserNotificationResponse:
        old_status = db_user.status

        db_user = await crud_modify_user(db, db_user, modified_user, groups=validated_groups)
        user = await self.update_user(db_user)

        logger.info(f'User "{user.username}" with id "{db_user.id}" modified by admin "{admin.username}"')

        asyncio.create_task(notification.modify_user(user, admin))

        if user.status != old_status:
            asyncio.create_task(notification.user_status_change(user, admin))

            old_status_value = getattr(old_status, "value", old_status)
            new_status_value = getattr(user.status, "value", user.status)
            logger.info(f'User "{db_user.username}" status changed from "{old_status_value}" to "{new_status_value}"')

        return user

    async def _set_user_disabled(
        self,
        db: AsyncSession,
        db_user: User,
        toggle: UserStatusToggle,
        admin: AdminDetails,
    ) -> UserResponse:
        old_status = db_user.status
        new_status = UserStatus.disabled if toggle.disabled else _resolve_enabled_user_status(db_user)

        if db_user.status != new_status:
            db_user.status = new_status
            db_user.last_status_change = dt.now(tz.utc)
            await db.commit()
            await load_user_attrs(db_user, load_admin_role=True)

        user = await self.update_user(db_user)

        if user.status != old_status:
            asyncio.create_task(notification.user_status_change(user, admin))
            old_status_value = getattr(old_status, "value", old_status)
            new_status_value = getattr(user.status, "value", user.status)
            logger.info(f'User "{user.username}" status changed from "{old_status_value}" to "{new_status_value}"')

        return user

    async def _modify_user(
        self,
        db: AsyncSession,
        db_user: User,
        modified_user: UserModify,
        admin: AdminDetails,
        *,
        skip_role_limits: bool = False,
    ) -> UserNotificationResponse:
        if not skip_role_limits:
            await self._enforce_manual_user_write_access(admin, db)

        validated_groups = await self._prepare_modified_user(
            db, db_user, modified_user, admin, skip_role_limits=skip_role_limits
        )
        return await self._apply_modified_user(db, db_user, modified_user, admin, validated_groups=validated_groups)

    async def modify_user(
        self, db: AsyncSession, username: str, modified_user: UserModify, admin: AdminDetails
    ) -> UserNotificationResponse:
        warnings.warn(
            "modify_user(username, ...) is deprecated and will be removed in v6.0.0. "
            "Use modify_user_by_id(user_id, ...).",
            DeprecationWarning,
            stacklevel=2,
        )
        db_user = await self.get_validated_user(db, username, admin)

        return await self._modify_user(db, db_user, modified_user, admin)

    async def modify_user_by_id(
        self, db: AsyncSession, user_id: int, modified_user: UserModify, admin: AdminDetails
    ) -> UserResponse:
        db_user = await self.get_validated_user_by_id(db, user_id, admin, scope_action="update")
        return await self._modify_user(db, db_user, modified_user, admin)

    async def set_user_disabled(
        self, db: AsyncSession, username: str, toggle: UserStatusToggle, admin: AdminDetails
    ) -> UserResponse:
        warnings.warn(
            "set_user_disabled(username, ...) is deprecated and will be removed in v6.0.0. "
            "Use set_user_disabled_by_id(user_id, ...).",
            DeprecationWarning,
            stacklevel=2,
        )
        db_user = await self.get_validated_user(db, username, admin, scope_action="update")
        return await self._set_user_disabled(db, db_user, toggle, admin)

    async def set_user_disabled_by_id(
        self, db: AsyncSession, user_id: int, toggle: UserStatusToggle, admin: AdminDetails
    ) -> UserResponse:
        db_user = await self.get_validated_user_by_id(db, user_id, admin, scope_action="update")
        return await self._set_user_disabled(db, db_user, toggle, admin)

    async def _remove_user(self, db: AsyncSession, db_user: User, admin: AdminDetails) -> dict:
        user = await self.validate_user(db_user, include_subscription_url=False)
        await remove_user(db, db_user)
        await sync_remove_user(user)

        asyncio.create_task(notification.remove_user(user, admin))
        logger.info(f'User "{db_user.username}" with id "{db_user.id}" deleted by admin "{admin.username}"')
        return {}

    async def remove_user(self, db: AsyncSession, username: str, admin: AdminDetails):
        warnings.warn(
            "remove_user(username, ...) is deprecated and will be removed in v6.0.0. "
            "Use remove_user_by_id(user_id, ...).",
            DeprecationWarning,
            stacklevel=2,
        )
        db_user = await self.get_validated_user(db, username, admin)
        return await self._remove_user(db, db_user, admin)

    async def remove_user_by_id(self, db: AsyncSession, user_id: int, admin: AdminDetails):
        db_user = await self.get_validated_user_by_id(db, user_id, admin, scope_action="delete")
        return await self._remove_user(db, db_user, admin)

    async def _get_validated_users_by_ids(
        self,
        db: AsyncSession,
        user_ids: list[int] | set[int],
        admin: AdminDetails,
        *,
        load_admin: bool = True,
        load_next_plan: bool = True,
        load_usage_logs: bool = True,
        load_groups: bool = True,
        load_admin_role: bool = False,
        scope_action: str = "read",
    ) -> list[User]:
        if not user_ids:
            return []

        ids_list = list(user_ids)

        # Replicate the scope filter that get_validated_user_by_id applies per-user.
        scope_admin_id = get_scope_admin_id(admin, "users", scope_action)
        query = UserListQuery(
            ids=ids_list,
            admin_ids=[scope_admin_id] if scope_admin_id is not None else None,
            limit=len(ids_list),
        )
        users = await get_users(db, query=query, load_admin_role=load_admin_role)

        # Verify every requested ID was found (mirrors the 404 in get_validated_user_by_id)
        found_ids = {user.id for user in users}
        missing = set(ids_list) - found_ids
        if missing:
            await self.raise_error(message="User not found", code=404)

        return users

    @staticmethod
    def _build_bulk_action_response(users: list[User | UserNotificationResponse]) -> BulkUsersActionResponse:
        usernames = [user.username for user in users]
        return BulkUsersActionResponse(users=usernames, count=len(usernames))

    async def _load_users_by_ids(self, db: AsyncSession, user_ids: list[int]) -> list[User]:
        return await get_users_by_ids(db, user_ids, load_admin_role=True)

    async def _load_users_by_usernames(self, db: AsyncSession, usernames: list[str]) -> list[User]:
        return await get_users_by_usernames(db, usernames, load_admin_role=True)

    async def bulk_remove_users(
        self, db: AsyncSession, bulk_users: BulkUsersSelection, admin: AdminDetails
    ) -> RemoveUsersResponse:
        db_users = await self._get_validated_users_by_ids(db, bulk_users.ids, admin, scope_action="delete")
        users = [await self.validate_user(db_user, include_subscription_url=False) for db_user in db_users]

        await remove_users(db, db_users)

        for user in users:
            await sync_remove_user(user)
            asyncio.create_task(notification.remove_user(user, admin))
            logger.info(f'User "{user.username}" with id "{user.id}" deleted by admin "{admin.username}"')

        return RemoveUsersResponse(users=[user.username for user in users], count=len(users))

    async def _reset_user_data_usage(
        self,
        db: AsyncSession,
        db_user: User,
        admin: AdminDetails,
        *,
        clean_chart_data: bool | None = None,
        emit_status_change_notification: bool = True,
    ):
        old_status = db_user.status

        if clean_chart_data is None:
            clean_chart_data = usage_settings.reset_user_usage_clean_chart_data

        db_user = await reset_user_data_usage(db=db, db_user=db_user, clean_chart_data=clean_chart_data)
        user = await self.update_user(db_user)

        if emit_status_change_notification and user.status != old_status:
            asyncio.create_task(notification.user_status_change(user, admin))

        asyncio.create_task(notification.reset_user_data_usage(user, admin))

        logger.info(f'User "{db_user.username}" usage was reset by admin "{admin.username}"')

        return user

    async def reset_user_data_usage(self, db: AsyncSession, username: str, admin: AdminDetails):
        warnings.warn(
            "reset_user_data_usage(username, ...) is deprecated and will be removed in v6.0.0. "
            "Use reset_user_data_usage_by_id(user_id, ...).",
            DeprecationWarning,
            stacklevel=2,
        )
        db_user = await self.get_validated_user(db, username, admin)

        return await self._reset_user_data_usage(db, db_user, admin)

    async def reset_user_data_usage_by_id(self, db: AsyncSession, user_id: int, admin: AdminDetails):
        db_user = await self.get_validated_user_by_id(db, user_id, admin, scope_action="update")
        return await self._reset_user_data_usage(db, db_user, admin)

    async def bulk_reset_user_data_usage(
        self, db: AsyncSession, bulk_users: BulkUsersSelection, admin: AdminDetails
    ) -> BulkUsersActionResponse:
        db_users = await self._get_validated_users_by_ids(
            db, bulk_users.ids, admin, load_usage_logs=False, scope_action="reset_usage"
        )
        old_statuses = {user.id: user.status for user in db_users}

        db_users = await bulk_reset_user_data_usage(
            db,
            db_users,
            clean_chart_data=usage_settings.reset_user_usage_clean_chart_data,
        )
        await sync_users(db_users)

        users = [await self.validate_user(db_user) for db_user in db_users]
        for user in users:
            if user.status != old_statuses[user.id]:
                asyncio.create_task(notification.user_status_change(user, admin))
            asyncio.create_task(notification.reset_user_data_usage(user, admin))
            logger.info(f'User "{user.username}" usage was reset by admin "{admin.username}"')

        return self._build_bulk_action_response(users)

    async def _revoke_user_sub(self, db: AsyncSession, db_user: User, admin: AdminDetails) -> UserResponse:
        proxy_settings = await self._prepare_revoked_proxy_settings(db, db_user)
        db_user = await revoke_user_sub(db=db, db_user=db_user, proxy_settings=proxy_settings.dict())
        user = await self.update_user(db_user)

        asyncio.create_task(notification.user_subscription_revoked(user, admin))
        logger.info(f'User "{db_user.username}" subscription was revoked by admin "{admin.username}"')

        return user

    async def revoke_user_sub(self, db: AsyncSession, username: str, admin: AdminDetails) -> UserResponse:
        warnings.warn(
            "revoke_user_sub(username, ...) is deprecated and will be removed in v6.0.0. "
            "Use revoke_user_sub_by_id(user_id, ...).",
            DeprecationWarning,
            stacklevel=2,
        )
        db_user = await self.get_validated_user(db, username, admin)
        return await self._revoke_user_sub(db, db_user, admin)

    async def revoke_user_sub_by_id(self, db: AsyncSession, user_id: int, admin: AdminDetails) -> UserResponse:
        db_user = await self.get_validated_user_by_id(
            db, user_id, admin, load_usage_logs=False, scope_action="revoke_sub"
        )
        return await self._revoke_user_sub(db, db_user, admin)

    async def bulk_revoke_user_sub(
        self, db: AsyncSession, bulk_users: BulkUsersSelection, admin: AdminDetails
    ) -> BulkUsersActionResponse:
        db_users = await self._get_validated_users_by_ids(
            db, bulk_users.ids, admin, load_usage_logs=False, scope_action="revoke_sub"
        )

        proxy_settings_by_user_id = {
            db_user.id: (await self._prepare_revoked_proxy_settings(db, db_user)).dict() for db_user in db_users
        }
        db_users = await bulk_revoke_user_sub(db, db_users, proxy_settings_by_user_id=proxy_settings_by_user_id)
        await sync_users(db_users)

        users = [await self.validate_user(db_user) for db_user in db_users]
        for user in users:
            asyncio.create_task(notification.user_subscription_revoked(user, admin))
            logger.info(f'User "{user.username}" subscription was revoked by admin "{admin.username}"')

        return self._build_bulk_action_response(users)

    async def _bulk_set_user_status(
        self, db: AsyncSession, db_users: list[User], status: UserStatus, admin: AdminDetails
    ) -> list[UserNotificationResponse]:
        if not db_users:
            return []

        prepared_updates = []
        for db_user in db_users:
            original_status = db_user.status
            modified_user = UserModify(status=status)
            validated_groups = await self._prepare_modified_user(db, db_user, modified_user, admin)
            prepared_updates.append((db_user, modified_user, validated_groups, original_status))

        modified_user_ids: list[int] = []
        try:
            for db_user, modified_user, validated_groups, _ in prepared_updates:
                await crud_modify_user(
                    db,
                    db_user,
                    modified_user,
                    groups=validated_groups,
                    commit=False,
                )
                if db_user.id is not None:
                    modified_user_ids.append(db_user.id)

            await db.commit()
        except Exception:
            await db.rollback()
            raise

        modified_db_users = await self._load_users_by_ids(db, modified_user_ids)
        await sync_users(modified_db_users)

        users = [await self.validate_user(db_user) for db_user in modified_db_users]
        users_by_id = {user.id: user for user in users}
        for db_user, _, _, original_status in prepared_updates:
            user = users_by_id.get(db_user.id)
            if user is None:
                continue
            asyncio.create_task(notification.modify_user(user, admin))
            logger.info(f'User "{user.username}" with id "{user.id}" modified by admin "{admin.username}"')
            if user.status != original_status:
                asyncio.create_task(notification.user_status_change(user, admin))
                old_status_value = getattr(original_status, "value", original_status)
                new_status_value = getattr(user.status, "value", user.status)
                logger.info(f'User "{user.username}" status changed from "{old_status_value}" to "{new_status_value}"')

        return users

    async def _bulk_set_users_disabled(
        self, db: AsyncSession, db_users: list[User], disabled: bool, admin: AdminDetails
    ) -> list[UserNotificationResponse]:
        if not db_users:
            return []

        changed_user_ids: list[int] = []
        original_statuses: dict[int, UserStatus] = {}
        changed_at = dt.now(tz.utc)

        try:
            for db_user in db_users:
                new_status = UserStatus.disabled if disabled else _resolve_enabled_user_status(db_user)
                if db_user.status == new_status:
                    continue
                if db_user.id is None:
                    continue
                original_statuses[db_user.id] = db_user.status
                db_user.status = new_status
                db_user.last_status_change = changed_at
                changed_user_ids.append(db_user.id)

            await db.commit()
        except Exception:
            await db.rollback()
            raise

        if changed_user_ids:
            changed_db_users = await self._load_users_by_ids(db, changed_user_ids)
            await sync_users(changed_db_users)
            users = [await self.validate_user(db_user) for db_user in changed_db_users]
        else:
            users = []

        for user in users:
            original_status = original_statuses.get(user.id)
            if original_status is None or user.status == original_status:
                continue
            asyncio.create_task(notification.user_status_change(user, admin))
            old_status_value = getattr(original_status, "value", original_status)
            new_status_value = getattr(user.status, "value", user.status)
            logger.info(f'User "{user.username}" status changed from "{old_status_value}" to "{new_status_value}"')

        return users

    async def bulk_disable_users(
        self, db: AsyncSession, bulk_users: BulkUsersSelection, admin: AdminDetails
    ) -> BulkUsersActionResponse:
        db_users = await self._get_validated_users_by_ids(
            db, bulk_users.ids, admin, load_usage_logs=False, scope_action="update"
        )
        users_to_disable = [db_user for db_user in db_users if db_user.status != UserStatus.disabled]

        users = await self._bulk_set_users_disabled(db, users_to_disable, True, admin)

        return self._build_bulk_action_response(users)

    async def bulk_enable_users(
        self, db: AsyncSession, bulk_users: BulkUsersSelection, admin: AdminDetails
    ) -> BulkUsersActionResponse:
        db_users = await self._get_validated_users_by_ids(
            db, bulk_users.ids, admin, load_usage_logs=False, scope_action="update"
        )
        users_to_enable = [db_user for db_user in db_users if db_user.status == UserStatus.disabled]

        users = await self._bulk_set_users_disabled(db, users_to_enable, False, admin)

        return self._build_bulk_action_response(users)

    async def reset_users_data_usage(self, db: AsyncSession, admin: AdminDetails):
        """Reset all users data usage — requires scope=all, resets every user."""
        await reset_all_users_data_usage(
            db=db,
            admin=None,  # None = all admins, not filtered by owner
            clean_chart_data=usage_settings.reset_user_usage_clean_chart_data,
        )

    async def _active_next_plan(self, db: AsyncSession, db_user: User, admin: AdminDetails) -> UserResponse:
        if db_user is None or db_user.next_plan is None:
            await self.raise_error(message="User doesn't have next plan", code=404)

        old_status = db_user.status
        db_user = await reset_user_by_next(
            db=db,
            db_user=db_user,
            clean_chart_data=usage_settings.reset_user_usage_clean_chart_data,
        )
        user = await self.update_user(db_user)

        if user.status != old_status:
            asyncio.create_task(notification.user_status_change(user, admin))

        asyncio.create_task(notification.user_data_reset_by_next(user, admin))
        logger.info(f'User "{db_user.username}"\'s usage was reset by next plan by admin "{admin.username}"')
        return user

    async def active_next_plan(self, db: AsyncSession, username: str, admin: AdminDetails) -> UserResponse:
        """Reset user by next plan"""
        warnings.warn(
            "active_next_plan(username, ...) is deprecated and will be removed in v6.0.0. "
            "Use active_next_plan_by_id(user_id, ...).",
            DeprecationWarning,
            stacklevel=2,
        )
        db_user = await self.get_validated_user(db, username, admin)
        return await self._active_next_plan(db, db_user, admin)

    async def active_next_plan_by_id(self, db: AsyncSession, user_id: int, admin: AdminDetails) -> UserResponse:
        db_user = await self.get_validated_user_by_id(db, user_id, admin, scope_action="update")
        return await self._active_next_plan(db, db_user, admin)

    async def _set_owner(self, db: AsyncSession, db_user: User, new_admin, admin: AdminDetails) -> UserResponse:
        db_user = await set_owner(db, db_user, new_admin)
        user = await self.validate_user(db_user)
        logger.info(
            f'User "{user.username}" owner successfully set to "{new_admin.username}" by admin "{admin.username}"'
        )
        return user

    async def set_owner(
        self, db: AsyncSession, username: str, admin_username: str, admin: AdminDetails
    ) -> UserResponse:
        """Set a new owner (admin) for a user."""
        warnings.warn(
            "set_owner(username, ...) is deprecated and will be removed in v6.0.0. Use set_owner_by_id(user_id, ...).",
            DeprecationWarning,
            stacklevel=2,
        )
        new_admin = await self.get_validated_admin(db, username=admin_username)
        db_user = await self.get_validated_user(db, username, admin)
        return await self._set_owner(db, db_user, new_admin, admin)

    async def set_owner_by_id(
        self, db: AsyncSession, user_id: int, admin_username: str, admin: AdminDetails
    ) -> UserResponse:
        new_admin = await self.get_validated_admin(db, username=admin_username)
        db_user = await self.get_validated_user_by_id(db, user_id, admin, scope_action="update")
        return await self._set_owner(db, db_user, new_admin, admin)

    async def bulk_set_owner(
        self, db: AsyncSession, bulk_users: BulkUsersSetOwner, admin: AdminDetails
    ) -> BulkUsersActionResponse:
        new_admin = await self.get_validated_admin(db, username=bulk_users.admin_username)
        db_users = await self._get_validated_users_by_ids(
            db, bulk_users.ids, admin, load_usage_logs=False, scope_action="update"
        )

        db_users = await bulk_set_owner(db, db_users, new_admin)
        users = [await self.validate_user(db_user) for db_user in db_users]
        for user in users:
            logger.info(
                f'User "{user.username}" owner successfully set to "{new_admin.username}" by admin "{admin.username}"'
            )

        return self._build_bulk_action_response(users)

    async def _get_user_usage(
        self,
        db: AsyncSession,
        db_user: User,
        admin: AdminDetails,
        start: dt = None,
        end: dt = None,
        period: Period = Period.hour,
        node_id: int | None = None,
        group_by_node: bool = False,
    ) -> UserUsageStatsList:
        start, end = await self.validate_dates(start, end, True)

        if not _has_permission(admin, "nodes", "stats"):
            node_id = None
            group_by_node = False

        return await get_user_usages(db, db_user.id, start, end, period, node_id=node_id, group_by_node=group_by_node)

    async def get_user_usage(
        self,
        db: AsyncSession,
        username: str,
        admin: AdminDetails,
        query: UserUsageQuery,
    ) -> UserUsageStatsList:
        warnings.warn(
            "get_user_usage(username, ...) is deprecated and will be removed in v6.0.0. "
            "Use get_user_usage_by_id(user_id, ...).",
            DeprecationWarning,
            stacklevel=2,
        )
        db_user = await self.get_validated_user(db, username, admin)
        return await self._get_user_usage(
            db,
            db_user,
            admin,
            query.start,
            query.end,
            query.period,
            query.node_id,
            query.group_by_node,
        )

    async def get_user_usage_by_id(
        self,
        db: AsyncSession,
        user_id: int,
        admin: AdminDetails,
        query: UserUsageQuery,
    ) -> UserUsageStatsList:
        db_user = await self.get_validated_user_by_id(db, user_id, admin)
        return await self._get_user_usage(
            db,
            db_user,
            admin,
            query.start,
            query.end,
            query.period,
            query.node_id,
            query.group_by_node,
        )

    async def get_user(self, db: AsyncSession, username: str, admin: AdminDetails) -> UserNotificationResponse:
        warnings.warn(
            "get_user(username, ...) is deprecated and will be removed in v6.0.0. Use get_user_by_id(user_id, ...).",
            DeprecationWarning,
            stacklevel=2,
        )
        db_user = await self.get_validated_user(db, username, admin)
        return await self.validate_user(db_user)

    async def get_user_by_id(self, db: AsyncSession, user_id: int, admin: AdminDetails) -> UserNotificationResponse:
        db_user = await self.get_validated_user_by_id(db, user_id, admin)
        return await self.validate_user(db_user)

    async def get_users(
        self,
        db: AsyncSession,
        admin: AdminDetails,
        query: UserListQuery,
    ) -> UsersResponse:
        """Get all users"""
        scope_admin_id = get_scope_admin_id(admin, "users", "read_simple")
        if scope_admin_id is not None:
            query = query.model_copy(update={"owner": [admin.username], "admin_ids": None})

        users, count = await get_users(
            db=db,
            query=query,
            return_with_count=True,
        )

        if query.load_sub:
            tasks = [self.generate_subscription_url(user) for user in users]
            urls = await asyncio.gather(*tasks)

            for user, url in zip(users, urls):
                user.subscription_url = url

        response = UsersResponse(users=users, total=count)

        return response

    async def get_users_simple(
        self,
        db: AsyncSession,
        admin: AdminDetails,
        query: UserSimpleListQuery,
    ) -> UsersSimpleResponse:
        """Get lightweight user list with only id and username"""
        scope_admin_id = get_scope_admin_id(admin, "users", "read")
        admin_filter = (
            None
            if scope_admin_id is None
            else await get_admin(db, admin.username, load_users=False, load_usage_logs=False)
        )

        # Call CRUD function
        rows, total = await get_users_simple(
            db=db,
            query=query,
            admin=admin_filter,
        )

        # Convert tuples to Pydantic models
        users = [UserSimple(id=row[0], username=row[1]) for row in rows]

        return UsersSimpleResponse(users=users, total=total)

    async def get_users_usage(
        self,
        db: AsyncSession,
        admin: AdminDetails,
        query: UsersUsageQuery,
    ) -> UserUsageStatsList:
        """Get all users usage"""
        start, end = await self.validate_dates(query.start, query.end, True)
        node_id = query.node_id
        group_by_node = query.group_by_node

        can_use_node_scope = _has_permission(admin, "nodes", "stats")
        if not can_use_node_scope:
            node_id = None
            group_by_node = False

        admins_filter = query.owner if is_scope_all(admin, "users", "read") else [admin.username]

        return await get_all_users_usages(
            db=db,
            start=start,
            end=end,
            period=query.period,
            node_id=node_id,
            admins=admins_filter,
            group_by_node=group_by_node,
        )

    async def get_users_count_metric(
        self,
        db: AsyncSession,
        admin: AdminDetails,
        metric: UserCountMetric,
        query: UsersUsageQuery,
    ) -> UserCountMetricStatsList:
        """Get one users activity/status count metric from usage rows."""
        start, end = await self.validate_dates(query.start, query.end, True)
        node_id = query.node_id
        group_by_node = query.group_by_node

        can_use_node_scope = _has_permission(admin, "nodes", "stats")
        if not can_use_node_scope:
            node_id = None
            group_by_node = False

        try:
            validate_user_count_metric_scope(metric, node_id=node_id, group_by_node=group_by_node)
        except ValueError as exc:
            await self.raise_error(message=str(exc), code=400)

        admins_filter = query.owner if is_scope_all(admin, "users", "read") else [admin.username]

        return await get_user_count_metric_stats(
            db=db,
            admins=admins_filter,
            start=start,
            end=end,
            period=query.period,
            metric=metric,
            node_id=node_id,
            group_by_node=group_by_node,
        )

    @staticmethod
    async def remove_users_logger(users: list[str], by: str):
        for user in users:
            logger.info(f'User "{user}" deleted by admin "{by}"')

    async def get_expired_users(
        self,
        db: AsyncSession,
        query: ExpiredUsersQuery,
    ) -> list[str]:
        """
        Get users who have expired within the specified date range.

        - **target**: `expired` (time-based) or `limited` (usage-based).
        - **expired_after** UTC datetime (optional)
        - **expired_before** UTC datetime (optional)
        - Date range filters are applied only when target is `expired`.
        - If both dates are omitted, returns all users matching target.
        """

        expired_after, expired_before = await self.validate_dates(query.expired_after, query.expired_before, False)
        if query.admin_username:
            admin_id = (await self.get_validated_admin(db, query.admin_username)).id
        else:
            admin_id = None
        users = await get_expired_users(
            db,
            query=query.model_copy(update={"expired_after": expired_after, "expired_before": expired_before}),
            admin_id=admin_id,
        )
        return [row.username for row in users]

    async def delete_expired_users(
        self,
        db: AsyncSession,
        admin: AdminDetails,
        query: ExpiredUsersQuery,
    ) -> RemoveUsersResponse:
        """
        Delete users who have expired within the specified date range.

        - **target**: `expired` (time-based) or `limited` (usage-based).
        - **expired_after** UTC datetime (optional)
        - **expired_before** UTC datetime (optional)
        - Date range filters are applied only when target is `expired`.
        """

        expired_after, expired_before = await self.validate_dates(query.expired_after, query.expired_before, False)

        if query.admin_username:
            admin_id = (await self.get_validated_admin(db, query.admin_username)).id
        else:
            admin_id = None
        username_list = await remove_expired_users(
            db,
            expired_after,
            expired_before,
            admin_id,
            target=query.target,
        )
        await self.remove_users_logger(users=username_list, by=admin.username)

        return RemoveUsersResponse(users=username_list, count=len(username_list))

    @staticmethod
    def load_base_user_args(template: UserTemplate) -> dict:
        user_args = {
            "data_limit": template.data_limit,
            "group_ids": template.group_ids,
            "data_limit_reset_strategy": template.data_limit_reset_strategy,
            "status": template.status,
            "hwid_limit": template.hwid_limit,
        }

        if template.status == UserStatus.active:
            if template.expire_duration:
                user_args["expire"] = dt.now(tz.utc) + td(seconds=template.expire_duration)
            else:
                user_args["expire"] = 0
        else:
            user_args["expire"] = 0
            user_args["on_hold_expire_duration"] = template.expire_duration
            if template.on_hold_timeout:
                user_args["on_hold_timeout"] = dt.now(tz.utc) + td(seconds=template.on_hold_timeout)
            else:
                user_args["on_hold_timeout"] = 0

        return user_args

    @staticmethod
    def apply_settings(user_args: UserCreate | UserModify, template: UserTemplate) -> UserCreate | UserModify:
        if template.extra_settings:
            method = template.extra_settings.get("method", None)

            if method is not None:
                user_args.proxy_settings.shadowsocks.method = method

        return user_args

    @staticmethod
    def _apply_template_username_affixes(username: str, user_template: UserTemplate) -> str:
        return (
            f"{user_template.username_prefix if user_template.username_prefix else ''}"
            f"{username}"
            f"{user_template.username_suffix if user_template.username_suffix else ''}"
        )

    def _build_user_create_from_template(
        self,
        user_template: UserTemplate,
        payload: CreateUserFromTemplate,
        apply_template_username_affixes: bool = True,
    ) -> UserCreate:
        new_user_args = self.load_base_user_args(user_template)
        username = payload.username
        if apply_template_username_affixes:
            username = self._apply_template_username_affixes(username, user_template)
        new_user_args["username"] = username

        try:
            new_user = UserCreate(**new_user_args, note=payload.note)
        except ValidationError as e:
            raise HTTPException(status_code=400, detail=self._format_validation_errors(e))

        new_user = self.apply_settings(new_user, user_template)

        return new_user

    async def create_user_from_template(
        self, db: AsyncSession, new_template_user: CreateUserFromTemplate, admin: AdminDetails
    ) -> UserResponse:
        user_template = await self._get_validated_template_with_access(db, new_template_user.user_template_id, admin)

        if user_template.is_disabled:
            await self.raise_error("this template is disabled", 403)

        try:
            new_user = self._build_user_create_from_template(user_template, new_template_user)
        except HTTPException as exc:
            raise exc

        # Template defines data_limit/expire/etc — only check max_users
        await self._enforce_user_limits(
            db,
            admin,
            check_max_users=True,
            require_finite_data_limit=False,
            require_finite_expire=False,
            require_finite_on_hold_timeout=False,
            require_finite_hwid_limit=False,
        )
        return await self.create_user(db, new_user, admin, skip_role_limits=True)

    async def _modify_user_with_template(
        self, db: AsyncSession, db_user: User, modified_template: ModifyUserByTemplate, admin: AdminDetails
    ) -> UserResponse:
        original_status = db_user.status
        user_template = await self._get_validated_template_with_access(db, modified_template.user_template_id, admin)

        if user_template.is_disabled:
            await self.raise_error("this template is disabled", 403)

        user_args = self.load_base_user_args(user_template)
        user_args["proxy_settings"] = db_user.proxy_settings

        try:
            modify_user = UserModify(**user_args, note=modified_template.note)
        except ValidationError as e:
            error_messages = "; ".join([f"{err['loc'][0]}: {err['msg']}" for err in e.errors()])
            await self.raise_error(message=error_messages, code=400)

        modify_user = self.apply_settings(modify_user, user_template)
        validated_groups = await self._prepare_modified_user(db, db_user, modify_user, admin, skip_role_limits=True)

        if user_template.reset_usages:
            suppress_reset_status_change = (
                user_template.status == UserStatus.on_hold and original_status != UserStatus.active
            )
            await self._reset_user_data_usage(
                db,
                db_user,
                admin,
                emit_status_change_notification=not suppress_reset_status_change,
            )

        return await self._apply_modified_user(db, db_user, modify_user, admin, validated_groups=validated_groups)

    async def modify_user_with_template(
        self, db: AsyncSession, username: str, modified_template: ModifyUserByTemplate, admin: AdminDetails
    ) -> UserResponse:
        warnings.warn(
            "modify_user_with_template(username, ...) is deprecated and will be removed in v6.0.0. "
            "Use modify_user_with_template_by_id(user_id, ...).",
            DeprecationWarning,
            stacklevel=2,
        )
        db_user = await self.get_validated_user(db, username, admin)
        return await self._modify_user_with_template(db, db_user, modified_template, admin)

    async def modify_user_with_template_by_id(
        self, db: AsyncSession, user_id: int, modified_template: ModifyUserByTemplate, admin: AdminDetails
    ) -> UserResponse:
        db_user = await self.get_validated_user_by_id(db, user_id, admin, scope_action="update")
        return await self._modify_user_with_template(db, db_user, modified_template, admin)

    async def bulk_create_users_from_template(
        self, db: AsyncSession, bulk_users: BulkUsersFromTemplate, admin: AdminDetails
    ) -> BulkUsersCreateResponse:
        template_payload = bulk_users
        user_template = await self._get_validated_template_with_access(db, template_payload.user_template_id, admin)

        if user_template.is_disabled:
            await self.raise_error("this template is disabled", 403)

        if bulk_users.strategy == UsernameGenerationStrategy.random:
            if template_payload.username not in (None, ""):
                await self.raise_error(message="username must be null when strategy is 'random'", code=400)
            base_username = None
        else:
            if not template_payload.username:
                await self.raise_error(message="username is required for sequence strategy", code=400)
            base_username = template_payload.username

        candidate_usernames = await self._generate_usernames(
            base_username=base_username,
            count=bulk_users.count,
            strategy=bulk_users.strategy,
            start_number=bulk_users.start_number,
            username_prefix=user_template.username_prefix,
            username_suffix=user_template.username_suffix,
        )

        def builder(username: str):
            payload = CreateUserFromTemplate(
                username=username,
                user_template_id=template_payload.user_template_id,
                note=template_payload.note,
            )
            return self._build_user_create_from_template(
                user_template,
                payload,
                apply_template_username_affixes=False,
            )

        users_to_create = self._build_bulk_user_models(candidate_usernames, builder)

        groups: list = []
        if users_to_create:
            groups = await self.validate_all_groups(db, users_to_create[0])

        db_admin = await get_admin(db, admin.username, load_users=False, load_usage_logs=False)
        try:
            subscription_urls = await self._persist_bulk_users(
                db,
                admin,
                db_admin,
                users_to_create,
                groups,
                skip_per_user_limits=True,
                commit=False,
                sync=False,
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise

        created_users = await self._load_users_by_usernames(db, [user.username for user in users_to_create])
        await sync_users(created_users)

        for db_user in created_users:
            user = await self.validate_user(db_user)
            asyncio.create_task(notification.create_user(user, admin))

        return BulkUsersCreateResponse(subscription_urls=subscription_urls, created=len(subscription_urls))

    async def bulk_apply_template_to_users(
        self,
        db: AsyncSession,
        body: BulkUsersApplyTemplate,
        admin: AdminDetails,
    ) -> BulkUsersActionResponse:
        db_users = await self._get_validated_users_by_ids(
            db, body.ids, admin, load_usage_logs=False, scope_action="update"
        )
        user_template = await self._get_validated_template_with_access(db, body.user_template_id, admin)

        if user_template.is_disabled:
            await self.raise_error("this template is disabled", 403)

        prepared_updates = []
        for db_user in db_users:
            original_status = db_user.status
            user_args = self.load_base_user_args(user_template)
            user_args["proxy_settings"] = db_user.proxy_settings

            try:
                modify_user = UserModify(**user_args, note=body.note)
            except ValidationError as e:
                error_messages = "; ".join([f"{err['loc'][0]}: {err['msg']}" for err in e.errors()])
                await self.raise_error(message=error_messages, code=400)

            modify_user = self.apply_settings(modify_user, user_template)
            validated_groups = await self._prepare_modified_user(db, db_user, modify_user, admin, skip_role_limits=True)
            emit_reset_status_change = not (
                user_template.status == UserStatus.on_hold and original_status != UserStatus.active
            )
            prepared_updates.append((db_user, modify_user, validated_groups, original_status, emit_reset_status_change))

        modified_user_ids: list[int] = []
        try:
            for db_user, modified_user_model, validated_groups, _, _ in prepared_updates:
                if user_template.reset_usages:
                    await reset_user_data_usage(
                        db,
                        db_user,
                        clean_chart_data=usage_settings.reset_user_usage_clean_chart_data,
                        commit=False,
                    )

                await crud_modify_user(
                    db,
                    db_user,
                    modified_user_model,
                    groups=validated_groups,
                    commit=False,
                )
                if db_user.id is not None:
                    modified_user_ids.append(db_user.id)

            await db.commit()
        except Exception:
            await db.rollback()
            raise

        modified_db_users = await self._load_users_by_ids(db, modified_user_ids)
        await sync_users(modified_db_users)

        users = [await self.validate_user(db_user) for db_user in modified_db_users]
        users_by_id = {user.id: user for user in users}
        for db_user, _, _, original_status, emit_reset_status_change in prepared_updates:
            user = users_by_id.get(db_user.id)
            if user is None:
                continue
            status_notification_sent = False
            if user_template.reset_usages:
                if emit_reset_status_change and user.status != original_status:
                    asyncio.create_task(notification.user_status_change(user, admin))
                    status_notification_sent = True
                asyncio.create_task(notification.reset_user_data_usage(user, admin))
                logger.info(f'User "{user.username}" usage was reset by admin "{admin.username}"')
            asyncio.create_task(notification.modify_user(user, admin))
            logger.info(f'User "{user.username}" with id "{user.id}" modified by admin "{admin.username}"')
            if user.status != original_status:
                if not status_notification_sent:
                    asyncio.create_task(notification.user_status_change(user, admin))
                old_status_value = getattr(original_status, "value", original_status)
                new_status_value = getattr(user.status, "value", user.status)
                logger.info(f'User "{user.username}" status changed from "{old_status_value}" to "{new_status_value}"')

        return self._build_bulk_action_response(users)

    async def bulk_modify_expire(self, db: AsyncSession, bulk_model: BulkUser):
        if bulk_model.dry_run:
            n = await count_bulk_expire_targets(db, bulk_model)
            return BulkOperationDryRunResponse(affected_users=n)
        users, users_count = await update_users_expire(db, bulk_model)
        await sync_users(users)

        if self.operator_type in (OperatorType.API, OperatorType.WEB):
            return {"detail": f"operation has been successfuly done on {users_count} users"}
        return users_count

    async def bulk_modify_datalimit(self, db: AsyncSession, bulk_model: BulkUser):
        if bulk_model.dry_run:
            n = await count_bulk_datalimit_targets(db, bulk_model)
            return BulkOperationDryRunResponse(affected_users=n)
        users, users_count = await update_users_datalimit(db, bulk_model)
        await sync_users(users)

        if self.operator_type in (OperatorType.API, OperatorType.WEB):
            return {"detail": f"operation has been successfuly done on {users_count} users"}
        return users_count

    async def bulk_modify_proxy_settings(self, db: AsyncSession, bulk_model: BulkUsersProxy):
        if bulk_model.method is None:
            await self.raise_error(message="No supported proxy settings were provided", code=400, db=db)
        if bulk_model.dry_run:
            n = await count_bulk_proxy_targets(db, bulk_model)
            return BulkOperationDryRunResponse(affected_users=n)
        users, users_count = await update_users_proxy_settings(db, bulk_model)
        await sync_users(users)

        if self.operator_type in (OperatorType.API, OperatorType.WEB):
            return {"detail": f"operation has been successfuly done on {users_count} users"}
        return users_count

    async def bulk_reallocate_wireguard_peer_ips(
        self, db: AsyncSession, body: BulkWireGuardPeerIPs, admin: AdminDetails
    ) -> WireGuardPeerIPsReallocateResponse:
        users = await get_bulk_wireguard_peer_ip_users(
            db,
            body,
            admin_id=get_scope_admin_id(admin, "users", "update"),
        )

        out = await run_bulk_reallocate_wireguard_peer_ips(
            db,
            users,
            dry_run=body.dry_run,
            replace_all=body.replace_all,
        )
        return WireGuardPeerIPsReallocateResponse(**out)

    async def _get_users_sub_update_list(
        self, db: AsyncSession, db_user: User, offset: int = 0, limit: int = 10
    ) -> UserSubscriptionUpdateList:
        user_sub_data, count = await get_users_sub_update_list(db, user_id=db_user.id, offset=offset, limit=limit)
        return UserSubscriptionUpdateList(updates=user_sub_data, count=count)

    async def get_users_sub_update_list(
        self, db: AsyncSession, username: str, admin: AdminDetails, offset: int = 0, limit: int = 10
    ) -> UserSubscriptionUpdateList:
        warnings.warn(
            "get_users_sub_update_list(username, ...) is deprecated and will be removed in v6.0.0. "
            "Use get_users_sub_update_list_by_id(user_id, ...).",
            DeprecationWarning,
            stacklevel=2,
        )
        db_user = await self.get_validated_user(db, username, admin)
        return await self._get_users_sub_update_list(db, db_user, offset, limit)

    async def get_users_sub_update_list_by_id(
        self, db: AsyncSession, user_id: int, admin: AdminDetails, offset: int = 0, limit: int = 10
    ) -> UserSubscriptionUpdateList:
        db_user = await self.get_validated_user_by_id(db, user_id, admin)
        return await self._get_users_sub_update_list(db, db_user, offset, limit)

    async def get_users_sub_update_chart(
        self,
        db: AsyncSession,
        admin: AdminDetails,
        user_id: int | None = None,
        username: str | None = None,
        admin_id: int | None = None,
    ) -> UserSubscriptionUpdateChart:
        if user_id is not None:
            db_user = await self.get_validated_user_by_id(db, user_id, admin)
            agent_counts = await get_users_subscription_agent_counts(db, user_id=db_user.id)
            return self._build_user_agent_chart(agent_counts)

        if username:
            warnings.warn(
                "username filter for get_users_sub_update_chart(...) is deprecated and will be removed in v6.0.0. "
                "Use user_id instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            db_user = await self.get_validated_user(db, username, admin)
            agent_counts = await get_users_subscription_agent_counts(db, user_id=db_user.id)
            return self._build_user_agent_chart(agent_counts)

        if admin_id:
            can_read_admins = False
            try:
                enforce_permission(admin, "admins", "read")
                can_read_admins = True
            except PermissionDenied:
                pass
            if not can_read_admins and admin_id != admin.id:
                await self.raise_error(message="You're not allowed", code=403)
            elif can_read_admins and admin_id != admin.id:
                await self.get_validated_admin_by_id(db, admin_id)
        else:
            admin_id = get_scope_admin_id(admin, "users", "read")

        agent_counts = await get_users_subscription_agent_counts(db, admin_id=admin_id)
        return self._build_user_agent_chart(agent_counts)

    @classmethod
    def _build_user_agent_chart(cls, agent_counts: list[tuple[str, int]]) -> UserSubscriptionUpdateChart:
        if not agent_counts:
            return UserSubscriptionUpdateChart(total=0, segments=[])

        counts = Counter()
        display_names: dict[str, str] = {}

        for agent, count in agent_counts:
            normalized = cls._normalize_user_agent(agent)
            key = normalized.lower()
            counts[key] += count
            display_names.setdefault(key, normalized)

        total = sum(counts.values())
        segments = [
            UserSubscriptionUpdateChartSegment(
                name=display_names[key],
                count=count,
                percentage=round((count / total) * 100, 2) if total else 0.0,
            )
            for key, count in counts.most_common()
        ]

        return UserSubscriptionUpdateChart(total=total, segments=segments)

    @staticmethod
    def _normalize_user_agent(user_agent: str) -> str:
        if not user_agent:
            return "Unknown"

        cleaned = user_agent.strip()
        if not cleaned:
            return "Unknown"

        tokens = [token for token in _USER_AGENT_SPLIT_RE.split(cleaned) if token]

        for token in tokens:
            if _VERSION_TOKEN_RE.fullmatch(token):
                continue

            sanitized = token.strip("-_")
            if sanitized:
                return sanitized

        return "Unknown"
