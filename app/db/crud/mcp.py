from datetime import UTC, datetime as dt, timedelta as td

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Admin, APIKey, MCPOAuthClient, MCPOAuthCode
from app.models.mcp import MCPKeySettings, MCPSettings


async def get_admin_mcp_settings(db: AsyncSession, admin_id: int) -> MCPSettings:
    value = (await db.execute(select(Admin.mcp).where(Admin.id == admin_id))).scalar_one_or_none()
    return MCPSettings.model_validate(value or {})


async def set_admin_mcp_settings(db: AsyncSession, db_admin: Admin, settings: MCPSettings) -> Admin:
    db_admin.mcp = settings.model_dump()
    await db.commit()
    await db.refresh(db_admin)
    return db_admin


async def get_api_key_with_admin(db: AsyncSession, key_id: int) -> APIKey | None:
    stmt = select(APIKey).where(APIKey.id == key_id).options(selectinload(APIKey.admin).selectinload(Admin.role))
    return (await db.execute(stmt)).scalar_one_or_none()


def api_key_mcp_settings(db_key: APIKey) -> MCPKeySettings:
    return MCPKeySettings.model_validate(db_key.mcp or {})


async def set_api_key_mcp_settings(db: AsyncSession, db_key: APIKey, settings: MCPKeySettings) -> APIKey:
    db_key.mcp = settings.model_dump()
    await db.commit()
    await db.refresh(db_key)
    return db_key


async def get_oauth_client(db: AsyncSession, client_id: str) -> MCPOAuthClient | None:
    return (await db.execute(select(MCPOAuthClient).where(MCPOAuthClient.client_id == client_id))).scalar_one_or_none()


async def create_oauth_client(
    db: AsyncSession,
    *,
    client_id: str,
    client_name: str | None,
    client_secret: str | None,
    redirect_uris: list[str],
    grant_types: list[str],
    token_endpoint_auth_method: str,
) -> MCPOAuthClient:
    db_client = MCPOAuthClient(
        client_id=client_id,
        client_name=client_name,
        client_secret=client_secret,
        redirect_uris=redirect_uris,
        grant_types=grant_types,
        token_endpoint_auth_method=token_endpoint_auth_method,
    )
    db.add(db_client)
    await db.commit()
    await db.refresh(db_client)
    return db_client


async def create_oauth_code(db: AsyncSession, db_code: MCPOAuthCode, keep_for: td) -> MCPOAuthCode:
    # Rows outlive the code so a consent request cannot be approved twice; drop them once that window is over
    await db.execute(delete(MCPOAuthCode).where(MCPOAuthCode.expires_at < dt.now(UTC) - keep_for))
    db.add(db_code)
    await db.commit()
    await db.refresh(db_code)
    return db_code


async def get_oauth_code(db: AsyncSession, code: str) -> MCPOAuthCode | None:
    return (await db.execute(select(MCPOAuthCode).where(MCPOAuthCode.code == code))).scalar_one_or_none()


async def use_oauth_code(db: AsyncSession, db_code: MCPOAuthCode) -> None:
    db_code.used_at = dt.now(UTC)
    await db.flush()


async def get_api_key_names(db: AsyncSession, admin_id: int, prefix: str) -> set[str]:
    stmt = select(APIKey.name).where(APIKey.admin_id == admin_id, APIKey.name.startswith(prefix))
    return set((await db.execute(stmt)).scalars())
