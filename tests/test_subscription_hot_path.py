"""Slim GET /sub user load and inbounds() reuse of already-loaded groups."""

from __future__ import annotations

import pytest
from sqlalchemy import event, inspect as sa_inspect, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload
from sqlalchemy.pool import StaticPool

from app.db import base
from app.db.crud.user import get_user_by_id
from app.db.models import Group, ProxyInbound, User, UserUsageResetLogs, users_groups_association
from app.operation.subscription import SubscriptionOperation


@pytest.fixture
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(base.Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as session:
        inbound = ProxyInbound(tag="vless-tcp")
        group = Group(name="g1", inbounds=[inbound])
        user = User(username="subuser", used_traffic=1000)
        session.add_all([inbound, group, user])
        await session.flush()
        await session.execute(users_groups_association.insert().values(user_id=user.id, groups_id=group.id))
        session.add(UserUsageResetLogs(user_id=user.id, used_traffic_at_reset=234))
        await session.commit()
        yield session, user.id, engine

    await engine.dispose()


@pytest.mark.asyncio
async def test_slim_user_fetch_skips_heavy_relations(db_session):
    session, user_id, _engine = db_session
    user = await get_user_by_id(
        session,
        user_id,
        load_admin=True,
        load_admin_role=True,
        load_next_plan=False,
        load_usage_logs=False,
        load_groups=False,
        load_lifetime_used_traffic=True,
    )
    assert user is not None
    unloaded = sa_inspect(user).unloaded
    assert "usage_logs" in unloaded
    assert "next_plan" in unloaded
    assert "groups" in unloaded
    assert user.lifetime_used_traffic == 1234
    assert "vless-tcp" in await user.inbounds()
    assert "groups" in sa_inspect(user).unloaded


@pytest.mark.asyncio
async def test_inbounds_skips_sql_when_groups_and_inbounds_are_loaded(db_session):
    session, user_id, engine = db_session
    user = (
        await session.execute(
            select(User).options(selectinload(User.groups).selectinload(Group.inbounds)).where(User.id == user_id)
        )
    ).scalar_one()

    select_count = 0

    def _count(_conn, _cursor, statement, *_args):
        nonlocal select_count
        if str(statement).lstrip().lower().startswith("select"):
            select_count += 1

    event.listen(engine.sync_engine, "before_cursor_execute", _count)
    try:
        tags = await user.inbounds()
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _count)

    assert tags == ["vless-tcp"]
    assert select_count == 0


@pytest.mark.asyncio
async def test_validated_user_uses_lifetime_expression(db_session):
    session, user_id, _engine = db_session
    db_user = await get_user_by_id(
        session,
        user_id,
        load_next_plan=False,
        load_usage_logs=False,
        load_groups=False,
        load_lifetime_used_traffic=True,
    )
    user = await SubscriptionOperation.validated_user(db_user)
    assert user.lifetime_used_traffic == 1234
    assert user.inbounds == ["vless-tcp"]


@pytest.mark.asyncio
async def test_subscription_and_headers_compute_rule_header_variables_once(db_session, monkeypatch: pytest.MonkeyPatch):
    from unittest.mock import AsyncMock

    from app.models.settings import ConfigFormat, SubRule, Subscription as SubSettings
    from app.operation import OperatorType

    session, user_id, _engine = db_session
    db_user = await get_user_by_id(
        session,
        user_id,
        load_admin=True,
        load_admin_role=True,
        load_next_plan=False,
        load_usage_logs=False,
        load_groups=False,
        load_lifetime_used_traffic=True,
    )

    sub_settings = SubSettings(
        profile_title="{BRAND} {USERNAME}",
        custom_variables=[
            {"key": "BRAND", "value": "Acme"},
            {"key": "COMBINED", "value": "{PROFILE_TITLE}|{format}|{url}"},
        ],
        response_headers={"x-sub-header": "{COMBINED}"},
        rules=[
            SubRule(
                pattern="^ClashMeta",
                target=ConfigFormat.clash_meta,
                response_headers={"x-rule-header": "{COMBINED}"},
            )
        ],
    )

    op = SubscriptionOperation(OperatorType.SYSTEM)
    monkeypatch.setattr("app.operation.subscription.subscription_settings", AsyncMock(return_value=sub_settings))
    monkeypatch.setattr(op, "get_validated_sub", AsyncMock(return_value=db_user))
    monkeypatch.setattr(op, "validate_and_register_hwid", AsyncMock())
    monkeypatch.setattr("app.operation.subscription.user_sub_update", AsyncMock())
    monkeypatch.setattr(op, "fetch_config", AsyncMock(return_value=("proxies: []", "text/yaml")))

    gen_url_mock = AsyncMock(return_value="https://sub.example.test/s/tok")
    monkeypatch.setattr("app.operation.subscription.UserOperation.generate_subscription_url", gen_url_mock)

    orig_get_vars = op._get_rule_response_header_variables
    vars_calls = 0

    async def tracked_get_vars(u, fmt):
        nonlocal vars_calls
        vars_calls += 1
        return await orig_get_vars(u, fmt)

    monkeypatch.setattr(op, "_get_rule_response_header_variables", tracked_get_vars)

    resp = await op.user_subscription(
        session,
        token="tok",
        accept_header="*/*",
        user_agent="ClashMeta/1.19",
        request_url="https://sub.example.test/s/tok",
    )
    expected = "Acme subuser|clash_meta|https://sub.example.test/s/tok"
    assert vars_calls == 1
    assert gen_url_mock.await_count == 1
    assert resp.headers["x-sub-header"] == expected
    assert resp.headers["x-rule-header"] == expected

    headers = await op.user_subscription_headers(
        session,
        token="tok",
        accept_header="*/*",
        user_agent="ClashMeta/1.19",
        request_url="https://sub.example.test/s/tok",
    )
    assert vars_calls == 2
    assert gen_url_mock.await_count == 2
    assert headers["x-sub-header"] == expected
    assert headers["x-rule-header"] == expected
