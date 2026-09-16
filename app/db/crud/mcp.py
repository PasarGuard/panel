from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MCPOAuthClient


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
