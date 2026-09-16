from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Admin, APIKey, MCPOAuthClient
from app.models.mcp import MCPKeySettings, MCPSettings


async def get_admin_mcp_settings(db: AsyncSession, admin_id: int) -> MCPSettings:
    value = (await db.execute(select(Admin.mcp).where(Admin.id == admin_id))).scalar_one_or_none()
    return MCPSettings.model_validate(value or {})


async def set_admin_mcp_settings(db: AsyncSession, db_admin: Admin, settings: MCPSettings) -> Admin:
    db_admin.mcp = settings.model_dump()
    await db.commit()
    await db.refresh(db_admin)
    return db_admin


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
