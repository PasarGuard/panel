from datetime import datetime as dt, timezone as tz

from sqlalchemy.exc import IntegrityError

from app.db import AsyncSession
from app.db.crud.admin_role import get_role
from app.db.crud.api_key import (
    create_api_key,
    delete_api_key,
    get_api_key_by_id,
    get_api_keys,
)
from app.models.admin import AdminDetails
from app.models.api_key import APIKeyCreate, APIKeyCreateResponse, APIKeyResponse, APIKeysQuery, APIKeysResponse
from app.operation import BaseOperation
from app.operation.permissions import get_effective_limits
from app.utils.system import readable_duration


class APIKeyOperation(BaseOperation):
    async def create_api_key(
        self, db: AsyncSession, *, admin: AdminDetails, model: APIKeyCreate
    ) -> APIKeyCreateResponse:
        if admin.id is None:
            await self.raise_error(message="API key creation is not available for env admins", code=403)

        role = await get_role(db, model.role_id)
        if role is None:
            await self.raise_error(message="Role not found", code=404)

        if not admin.is_owner and admin.role and role.id != admin.role.id:
            await self.raise_error(message="Only owner can create API keys with a different role", code=403)

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
        except IntegrityError:
            await self.raise_error(message="API key already exists", code=409, db=db)

        return APIKeyCreateResponse(
            id=db_key.id,
            admin_id=db_key.admin_id,
            name=db_key.name,
            note=db_key.note,
            role_id=db_key.role_id,
            created_at=db_key.created_at,
            expire_date=db_key.expire_date,
            api_key=raw_key,
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

        await delete_api_key(db, db_key)
        await db.commit()
