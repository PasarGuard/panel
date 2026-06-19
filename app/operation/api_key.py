from datetime import datetime as dt, timezone as tz

from sqlalchemy.exc import IntegrityError

from app.db import AsyncSession
from app.db.crud.api_key import (
    create_api_key,
    delete_api_key,
    get_api_key_by_id,
    get_api_keys,
    revoke_api_key as revoke_api_key_crud,
    update_api_key,
)
from app.notification import (
    create_api_key as notify_create,
    modify_api_key as notify_modify,
    remove_api_key as notify_delete,
)
from app.models.admin import AdminDetails
from app.models.admin_role import RolePermissions
from app.models.api_key import (
    APIKeyCreate,
    APIKeyCreateResponse,
    APIKeyResponse,
    APIKeyUpdate,
    APIKeysQuery,
    APIKeysResponse,
)
from app.operation import BaseOperation


def _check_permissions_not_exceed_admin(admin: AdminDetails, requested: RolePermissions) -> None:
    """Raise ValueError if any permission in `requested` exceeds what `admin` has.

    Owners are exempt — they can assign any permissions.
    """
    if admin.is_owner:
        return

    admin_perms = admin.role.permissions if admin.role else RolePermissions()

    for resource_name, resource_perms in requested.model_dump(exclude_none=True).items():
        if resource_perms is None:
            continue
        admin_resource = admin_perms.get(resource_name)
        if admin_resource is None:
            raise ValueError(f"You don't have access to resource '{resource_name}'")

        for action, value in resource_perms.items():
            if value is None:
                continue
            admin_action = admin_resource.get(action) if admin_resource else None
            if admin_action is None:
                raise ValueError(
                    f"You don't have the '{action}' permission on '{resource_name}'"
                )
            # True means unrestricted — cannot grant if admin only has scoped access
            if value is True and admin_action is not True:
                raise ValueError(
                    f"Cannot grant '{resource_name}.{action}=True': "
                    f"your own access is scoped (scope={admin_action.get('scope', 0) if isinstance(admin_action, dict) else admin_action})"
                )
            # If both sides have a scope dict, key scope must not exceed admin scope
            if isinstance(value, dict) and isinstance(admin_action, dict):
                key_scope = value.get("scope", 0)
                admin_scope = admin_action.get("scope", 0)
                if key_scope > admin_scope:
                    raise ValueError(
                        f"Cannot grant '{resource_name}.{action}' with scope={key_scope}: "
                        f"your scope is {admin_scope}"
                    )


class APIKeyOperation(BaseOperation):
    async def create_api_key(
        self, db: AsyncSession, *, admin: AdminDetails, model: APIKeyCreate
    ) -> APIKeyCreateResponse:
        if admin.id is None:
            await self.raise_error(message="API key creation is not available for env admins", code=403)

        if not model.inherit_permissions:
            try:
                _check_permissions_not_exceed_admin(admin, model.permissions)
            except ValueError as exc:
                await self.raise_error(message=str(exc), code=403)

        duplicates, _ = await get_api_keys(db, admin_id=admin.id, offset=0, limit=1, name=model.name)
        if duplicates:
            await self.raise_error(message="API key name already exists", code=409)

        if model.expire_date is not None and model.expire_date <= dt.now(tz.utc):
            await self.raise_error(message="expire_date must be in the future", code=422)

        try:
            raw_key, db_key = await create_api_key(
                db,
                admin_id=admin.id,
                model=model,
            )
            await db.commit()
            await notify_create(APIKeyResponse.model_validate(db_key), admin.username, admin.username)
        except IntegrityError:
            await self.raise_error(message="API key already exists", code=409, db=db)

        return APIKeyCreateResponse(
            id=db_key.id,
            admin_id=db_key.admin_id,
            name=db_key.name,
            note=db_key.note,
            permissions=RolePermissions.model_validate(db_key.permissions),
            inherit_permissions=db_key.inherit_permissions,
            created_at=db_key.created_at,
            expire_date=db_key.expire_date,
            revoked_at=db_key.revoked_at,
            status=db_key.status,
            is_expired=db_key.is_expired,
            api_key=raw_key,
            api_key_trimmed=db_key.api_key_trimmed,
        )

    async def list_api_keys(self, db: AsyncSession, *, admin: AdminDetails, query: APIKeysQuery) -> APIKeysResponse:
        scope_admin_id = None if admin.is_owner else admin.id
        rows, total = await get_api_keys(
            db,
            admin_id=scope_admin_id,
            offset=query.offset,
            limit=query.limit,
            key_id=query.key_id,
            name=query.name,
            status=query.status,
        )
        return APIKeysResponse(api_keys=[APIKeyResponse.model_validate(row) for row in rows], total=total)

    async def modify_api_key(
        self, db: AsyncSession, *, admin: AdminDetails, key_id: int, model: APIKeyUpdate
    ) -> APIKeyResponse:
        db_key = await get_api_key_by_id(db, key_id)
        if db_key is None:
            await self.raise_error(message="API key not found", code=404)

        if not admin.is_owner and db_key.admin_id != admin.id:
            await self.raise_error(message="Permission denied", code=403)

        if model.name is not None and model.name != db_key.name:
            duplicates, _ = await get_api_keys(db, admin_id=db_key.admin_id, offset=0, limit=1, name=model.name)
            if duplicates:
                await self.raise_error(message="API key name already exists", code=409)

        uses_custom_permissions = model.inherit_permissions is False or (
            model.inherit_permissions is None and model.permissions is not None and not db_key.inherit_permissions
        )

        if model.permissions is not None and uses_custom_permissions:
            try:
                _check_permissions_not_exceed_admin(admin, model.permissions)
            except ValueError as exc:
                await self.raise_error(message=str(exc), code=403)

        update_data = model.model_dump(exclude_unset=True)
        if update_data.get("inherit_permissions") is True:
            update_data["permissions"] = {}
        # Serialize permissions to plain dict for DB storage
        if "permissions" in update_data and isinstance(update_data["permissions"], RolePermissions):
            update_data["permissions"] = update_data["permissions"].model_dump(exclude_none=True)
        elif "permissions" in update_data and model.permissions is not None:
            update_data["permissions"] = model.permissions.model_dump(exclude_none=True)

        db_key = await update_api_key(db, db_key, update_data)
        await db.commit()

        api_key_resp = APIKeyResponse.model_validate(db_key)
        admin_username = db_key.admin.username if db_key.admin else "Unknown"
        await notify_modify(api_key_resp, admin_username, admin.username)

        return api_key_resp

    async def revoke_api_key(self, db: AsyncSession, *, admin: AdminDetails, key_id: int) -> APIKeyCreateResponse:
        db_key = await get_api_key_by_id(db, key_id)
        if db_key is None:
            await self.raise_error(message="API key not found", code=404)

        if not admin.is_owner and db_key.admin_id != admin.id:
            await self.raise_error(message="Permission denied", code=403)

        raw_key, db_key = await revoke_api_key_crud(db, db_key)
        await db.commit()

        api_key_resp = APIKeyResponse.model_validate(db_key)
        admin_username = db_key.admin.username if db_key.admin else "Unknown"
        await notify_modify(api_key_resp, admin_username, admin.username)

        return APIKeyCreateResponse(
            id=db_key.id,
            admin_id=db_key.admin_id,
            name=db_key.name,
            note=db_key.note,
            permissions=RolePermissions.model_validate(db_key.permissions),
            inherit_permissions=db_key.inherit_permissions,
            created_at=db_key.created_at,
            expire_date=db_key.expire_date,
            revoked_at=db_key.revoked_at,
            status=db_key.status,
            is_expired=db_key.is_expired,
            api_key=raw_key,
            api_key_trimmed=db_key.api_key_trimmed,
        )

    async def get_api_key(self, db: AsyncSession, *, admin: AdminDetails, key_id: int) -> APIKeyResponse:
        scope_admin_id = None if admin.is_owner else admin.id
        rows, _ = await get_api_keys(db, admin_id=scope_admin_id, offset=0, limit=1, key_id=key_id)
        if not rows:
            await self.raise_error(message="API key not found", code=404)
        return APIKeyResponse.model_validate(rows[0])

    async def delete_api_key(self, db: AsyncSession, *, admin: AdminDetails, key_id: int) -> None:
        db_key = await get_api_key_by_id(db, key_id)
        if db_key is None:
            await self.raise_error(message="API key not found", code=404)

        if not admin.is_owner and db_key.admin_id != admin.id:
            await self.raise_error(message="Permission denied", code=403)

        api_key_resp = APIKeyResponse.model_validate(db_key)
        admin_username = db_key.admin.username if db_key.admin else "Unknown"

        await delete_api_key(db, db_key)
        await db.commit()
        await notify_delete(api_key_resp, admin_username, admin.username)
