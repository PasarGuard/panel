from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models import Base, Node, User
from app.models.node import NodeResponse
from app.models.user import UserResponse


def _node(name: str) -> Node:
    return Node(
        name=name,
        address="127.0.0.1",
        port=62050,
        api_port=62051,
        server_ca="ca",
        api_key=None,
        core_config_id=None,
    )


@pytest.mark.asyncio
async def test_sqlite_reused_numeric_id_gets_new_bridge_namespace(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'nodes.db'}")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as db:
            first = _node("first")
            db.add(first)
            await db.commit()
            first_id = first.id
            first_bridge_id = first.bridge_id

            await db.delete(first)
            await db.commit()

            replacement = _node("replacement")
            db.add(replacement)
            await db.commit()

            assert replacement.id == first_id
            assert replacement.bridge_id != first_bridge_id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sqlite_reused_user_id_gets_new_sync_incarnation(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'users.db'}")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as db:
            first = User(username="first")
            db.add(first)
            await db.commit()
            first_id = first.id
            first_sync_id = first.sync_id

            await db.delete(first)
            await db.commit()

            replacement = User(username="replacement")
            db.add(replacement)
            await db.commit()

            assert replacement.id == first_id
            assert replacement.sync_id != first_sync_id
    finally:
        await engine.dispose()


def test_internal_sync_namespaces_are_not_part_of_public_api_schemas():
    assert "bridge_id" not in NodeResponse.model_json_schema()["properties"]
    assert "sync_id" not in UserResponse.model_json_schema()["properties"]
