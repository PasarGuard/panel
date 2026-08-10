import asyncio
import json
import os
import subprocess
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.hosts import HostManager
from app.db.crud.settings import lock_settings_row
from app.db.models import ClientTemplate, ProxyHost, Settings, UserStatus
from app.models.client_template import BulkClientTemplateSelection
from app.models.host import SubscriptionTemplates
from app.models.settings import ConfigFormat, SubRule
from app.models.subscription import (
    GRPCTransportConfig,
    SubscriptionInboundData,
    TCPTransportConfig,
    TLSConfig,
    WebSocketTransportConfig,
    XHTTPTransportConfig,
)
from app.models.subscription_profile import ProfileClient, ProfilePool, SubscriptionProfile
from app.operation import OperatorType
from app.operation.client_template import ClientTemplateOperation
from app.operation.host import HostOperation
from app.operation.subscription import SubscriptionOperation
from app.subscription.profiles import (
    ProfileValidationError,
    _retag_xray_outbounds,
    build_singbox_profile,
    build_xray_profile,
    endpoint_from_inbound,
    validate_profile_routing_rules,
)
from app.subscription.share import generate_subscription, generate_subscription_profile


def test_legacy_host_template_response_omits_empty_profile_classification():
    assert SubscriptionTemplates(xray=42).model_dump() == {"xray": 42}


def test_host_profile_country_normalizes_optional_input_before_length_validation():
    assert SubscriptionTemplates.model_validate({"profile": {"country": " de "}}).profile.country == "DE"
    assert SubscriptionTemplates.model_validate({"profile": {"country": "   "}}).profile.country is None


@pytest.mark.parametrize("invalid_country", [1, [], {}])
def test_host_profile_country_rejects_non_strings_without_internal_error(invalid_country):
    with pytest.raises(ValueError, match="country must be a two-letter ISO code"):
        SubscriptionTemplates.model_validate({"profile": {"country": invalid_country}})


def test_profile_health_timeout_must_not_be_shorter_than_interval():
    with pytest.raises(ValueError, match="timeout must be greater"):
        SubscriptionProfile.model_validate({"health_check": {"interval": "3m", "timeout": "5s"}})


def test_profile_routing_rules_are_checked_for_the_selected_engine():
    xray_profile = SubscriptionProfile(routing_rules=[{"type": "field", "domain": ["example.com"]}])
    singbox_profile = SubscriptionProfile(routing_rules=[{"action": "route", "outbound": "direct"}])

    with pytest.raises(ProfileValidationError, match="outboundTag or balancerTag"):
        validate_profile_routing_rules(xray_profile, "xray")
    with pytest.raises(ProfileValidationError, match="Sing-box action or outbound"):
        validate_profile_routing_rules(SubscriptionProfile(routing_rules=[{"domain": ["example.com"]}]), "sing_box")
    validate_profile_routing_rules(
        SubscriptionProfile(routing_rules=[{"type": "field", "domain": ["example.com"], "outboundTag": "direct"}]),
        "xray",
    )
    validate_profile_routing_rules(singbox_profile, "sing_box")


def make_endpoint(
    pool: str,
    country: str,
    *,
    remark: str = "mutable display name",
    host_id: int = 1,
    exclude_from_auto: bool = False,
    priority: int | None = None,
):
    inbound = SubscriptionInboundData(
        remark=remark,
        host_id=host_id,
        inbound_tag=f"vless-{pool}-{country}",
        protocol="vless",
        address=["edge.example.test"],
        port=443,
        network="tcp",
        tls_config=TLSConfig(
            tls="reality",
            sni="www.example.com",
            fingerprint="chrome",
            reality_public_key="TNu8kzI7cb1blwIV2IgIpeT7CnlM0ymyhD3eblxbtHo",
            reality_short_id="abcd",
        ),
        transport_config=TCPTransportConfig(),
        profile_classification={
            "pool": pool,
            "country": country,
            "exclude_from_auto": exclude_from_auto,
            "priority": priority,
        },
    )
    return endpoint_from_inbound(inbound, "edge.example.test", {"id": "11111111-1111-1111-1111-111111111111"})


def make_vless_transport_endpoint(network: str, *, host_id: int, pool: str = "primary"):
    transport_config = {
        "tcp": TCPTransportConfig(),
        "ws": WebSocketTransportConfig(path="/websocket", host="cdn.example.test"),
        "grpc": GRPCTransportConfig(path="grpc-service", host="cdn.example.test"),
        "xhttp": XHTTPTransportConfig(path="/xhttp", host="cdn.example.test", mode="auto"),
    }[network]
    tls_config = TLSConfig(
        tls="reality",
        sni="www.example.com",
        fingerprint="chrome",
        reality_public_key="TNu8kzI7cb1blwIV2IgIpeT7CnlM0ymyhD3eblxbtHo",
        reality_short_id="0123456789abcdef",
    )
    if network == "ws":
        tls_config = TLSConfig(tls="tls", sni="www.example.com", fingerprint="chrome")
    inbound = SubscriptionInboundData(
        remark=f"VLESS Reality {network}",
        host_id=host_id,
        inbound_tag=f"vless-{network}-{host_id}",
        protocol="vless",
        address=["edge.example.test"],
        port=443,
        network=network,
        tls_config=tls_config,
        transport_config=transport_config,
        profile_classification={"pool": pool, "country": "de" if pool == "primary" else "fi"},
    )
    return endpoint_from_inbound(inbound, "edge.example.test", {"id": "11111111-1111-1111-1111-111111111111"})


def make_wireguard_endpoint(*, host_id: int, pool: str = "primary"):
    inbound = SubscriptionInboundData(
        remark="WireGuard",
        host_id=host_id,
        inbound_tag=f"wireguard-{host_id}",
        protocol="wireguard",
        address=["wg.example.test"],
        port=51820,
        network="tcp",
        tls_config=TLSConfig(),
        transport_config=TCPTransportConfig(),
        wireguard_public_key="Pzte147TjrfehJYJJW6NutMXNSv5sEKevN/9yB7BHiI=",
        wireguard_allowed_ips=["0.0.0.0/0", "::/0"],
        profile_classification={"pool": pool, "country": "de" if pool == "primary" else "fi"},
    )
    return endpoint_from_inbound(
        inbound,
        "wg.example.test",
        {
            "private_key": "SECt7M+AG5pyjI3H3nFKrknvDWwt4I76Od66segwolw=",
            "peer_ips": ["10.0.0.2/32"],
        },
    )


def profile():
    return SubscriptionProfile(
        default_pool="primary",
        pools=[ProfilePool(id="primary", fallback_pool="fallback"), ProfilePool(id="fallback")],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [UserStatus.disabled, UserStatus.expired, UserStatus.limited])
async def test_profile_generator_leaves_user_eligibility_to_public_routes(status, monkeypatch):
    monkeypatch.setattr(
        "app.subscription.share.subscription_settings",
        AsyncMock(return_value=SimpleNamespace(custom_variables=[])),
    )
    monkeypatch.setattr("app.subscription.share.setup_format_variables", lambda *_: {})
    monkeypatch.setattr("app.subscription.share.get_effective_custom_variables", lambda *_: [])
    monkeypatch.setattr("app.subscription.share.host_manager.get_hosts", AsyncMock(return_value={}))

    user = SimpleNamespace(id=1, status=status, proxy_settings=SimpleNamespace(dict=dict), inbounds=[])
    with pytest.raises(ProfileValidationError, match="No eligible endpoints"):
        await generate_subscription_profile(
            user,
            '{"default_pool":"primary","pools":[{"id":"primary"}]}',
            "xray",
        )


@pytest.mark.asyncio
async def test_profile_preserves_on_hold_subscription_eligibility(monkeypatch):
    monkeypatch.setattr(
        "app.subscription.share.subscription_settings",
        AsyncMock(return_value=SimpleNamespace(custom_variables=[])),
    )
    monkeypatch.setattr("app.subscription.share.setup_format_variables", lambda *_: {})
    monkeypatch.setattr("app.subscription.share.get_effective_custom_variables", lambda *_: [])
    monkeypatch.setattr("app.subscription.share.host_manager.get_hosts", AsyncMock(return_value={}))

    user = SimpleNamespace(
        id=1,
        status=UserStatus.on_hold,
        proxy_settings=SimpleNamespace(dict=dict),
        inbounds=[],
    )
    with pytest.raises(ProfileValidationError, match="No eligible endpoints"):
        await generate_subscription_profile(
            user,
            '{"default_pool":"primary","pools":[{"id":"primary"}]}',
            "xray",
        )


@pytest.mark.asyncio
async def test_profile_reference_lock_prevents_delete_update_toctou(tmp_path):
    database_path = (tmp_path / "profile-reference-lock.db").as_posix()
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}", connect_args={"timeout": 5})
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: Settings.__table__.create(sync, checkfirst=True))
        await connection.run_sync(lambda sync: ClientTemplate.__table__.create(sync, checkfirst=True))
        await connection.execute(
            insert(Settings).values(
                id=1,
                telegram={},
                webhook={},
                notification_settings={},
                notification_enable={},
                subscription={"rules": []},
                hwid={},
                general={},
            )
        )
        await connection.execute(
            insert(ClientTemplate).values(
                id=1,
                name="profile",
                template_type="xray_profile",
                content='{"default_pool":"primary","pools":[{"id":"primary"}]}',
                is_default=False,
                is_system=False,
            )
        )

    delete_has_lock = asyncio.Event()
    allow_delete_commit = asyncio.Event()

    async def delete_profile():
        async with session_factory() as session:
            await lock_settings_row(session)
            delete_has_lock.set()
            await allow_delete_commit.wait()
            await session.execute(delete(ClientTemplate).where(ClientTemplate.id == 1))
            await session.commit()

    async def update_settings() -> bool:
        await delete_has_lock.wait()
        async with session_factory() as session:
            settings = await lock_settings_row(session)
            template_id = (
                await session.execute(select(ClientTemplate.id).where(ClientTemplate.id == 1))
            ).scalar_one_or_none()
            if template_id is None:
                await session.rollback()
                return False
            settings.subscription = {"rules": [{"pattern": ".*", "target": "xray", "profile_id": 1}]}
            await session.commit()
            return True

    delete_task = asyncio.create_task(delete_profile())
    await delete_has_lock.wait()
    update_task = asyncio.create_task(update_settings())
    allow_delete_commit.set()

    await delete_task
    assert await update_task is False
    await engine.dispose()


@pytest.mark.asyncio
async def test_template_delete_acquires_reference_lock_before_reading_replacement(monkeypatch):
    events = []
    operation = ClientTemplateOperation(OperatorType.API)

    async def record_lock(_db):
        events.append("lock")

    async def stop_after_read(_db, _template_id):
        assert events == ["lock"]
        raise RuntimeError("read reached")

    monkeypatch.setattr("app.operation.client_template.lock_settings_row", record_lock)
    monkeypatch.setattr(operation, "get_validated_client_template", stop_after_read)

    with pytest.raises(RuntimeError, match="read reached"):
        await operation.remove_client_template(SimpleNamespace(), 1, SimpleNamespace(username="admin"))


@pytest.mark.asyncio
@pytest.mark.parametrize("method_name", ["create_host", "modify_host", "modify_hosts"])
async def test_host_template_mutations_lock_before_validating_json_reference(method_name, monkeypatch):
    events = []
    operation = HostOperation(OperatorType.API)
    host = SimpleNamespace(id=1)

    async def record_lock(_db):
        events.append("lock")

    async def stop_after_validation(_db, _host):
        assert events == ["lock"]
        raise RuntimeError("validation reached")

    monkeypatch.setattr("app.operation.host.lock_settings_row", record_lock)
    monkeypatch.setattr(operation, "validate_subscription_templates", stop_after_validation)

    with pytest.raises(RuntimeError, match="validation reached"):
        if method_name == "create_host":
            await operation.create_host(SimpleNamespace(), host, SimpleNamespace(username="admin"))
        elif method_name == "modify_host":
            await operation.modify_host(SimpleNamespace(), 1, host, SimpleNamespace(username="admin"))
        else:
            await operation.modify_hosts(SimpleNamespace(), [host], SimpleNamespace(username="admin"))


@pytest.mark.asyncio
async def test_concurrent_default_and_replacement_deletes_leave_a_default(tmp_path, monkeypatch):
    database_path = (tmp_path / "profile-default-delete-lock.db").as_posix()
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}", connect_args={"timeout": 5})
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: Settings.__table__.create(sync, checkfirst=True))
        await connection.run_sync(lambda sync: ClientTemplate.__table__.create(sync, checkfirst=True))
        await connection.run_sync(lambda sync: ProxyHost.__table__.create(sync, checkfirst=True))
        await connection.execute(
            insert(Settings).values(
                id=1,
                telegram={},
                webhook={},
                notification_settings={},
                notification_enable={},
                subscription={"rules": []},
                hwid={},
                general={},
            )
        )
        await connection.execute(
            insert(ClientTemplate),
            [
                {
                    "id": template_id,
                    "name": name,
                    "template_type": "xray_profile",
                    "content": '{"default_pool":"primary","pools":[{"id":"primary"}]}',
                    "is_default": is_default,
                    "is_system": False,
                }
                for template_id, name, is_default in (
                    (1, "default", True),
                    (2, "replacement", False),
                    (3, "survivor", False),
                )
            ],
        )

    monkeypatch.setattr(ClientTemplateOperation, "_sync_client_template_cache", AsyncMock())

    async def remove(template_id: int):
        async with session_factory() as session:
            await ClientTemplateOperation(OperatorType.API).remove_client_template(
                session,
                template_id,
                SimpleNamespace(username="admin"),
            )

    await asyncio.gather(remove(1), remove(2))

    async with session_factory() as session:
        survivors = (
            await session.execute(select(ClientTemplate.id, ClientTemplate.is_default).order_by(ClientTemplate.id))
        ).all()
    assert survivors == [(3, True)]
    await engine.dispose()


@pytest.mark.asyncio
async def test_referenced_bulk_delete_leaves_all_database_state_unchanged(tmp_path):
    database_path = (tmp_path / "referenced-bulk-delete.db").as_posix()
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: Settings.__table__.create(sync, checkfirst=True))
        await connection.run_sync(lambda sync: ClientTemplate.__table__.create(sync, checkfirst=True))
        await connection.run_sync(lambda sync: ProxyHost.__table__.create(sync, checkfirst=True))

    async with session_factory() as session:
        session.add(
            Settings(
                telegram={},
                webhook={},
                notification_settings={},
                notification_enable={},
                subscription={"rules": [{"pattern": ".*", "target": "xray", "profile_id": 1}]},
                hwid={},
                general={},
            )
        )
        session.add_all(
            [
                ClientTemplate(
                    name="referenced-profile",
                    template_type="xray_profile",
                    content='{"default_pool":"primary","pools":[{"id":"primary"}]}',
                    is_default=True,
                    is_system=False,
                ),
                ClientTemplate(
                    name="replacement-profile",
                    template_type="xray_profile",
                    content='{"default_pool":"primary","pools":[{"id":"primary"}]}',
                    is_default=False,
                    is_system=False,
                ),
                ProxyHost(
                    remark="profile-host",
                    port=None,
                    path=None,
                    priority=1,
                    allowinsecure=None,
                    address={"example.test"},
                    alpn=[],
                    status=[],
                    subscription_templates={"xray": 1},
                ),
            ]
        )
        await session.commit()

        async def snapshot_state():
            settings = (await session.execute(select(Settings))).scalar_one()
            templates = (
                await session.execute(
                    select(
                        ClientTemplate.id,
                        ClientTemplate.name,
                        ClientTemplate.is_default,
                    ).order_by(ClientTemplate.id)
                )
            ).all()
            host_templates = (await session.execute(select(ProxyHost.subscription_templates))).scalar_one()
            return settings.subscription, templates, host_templates

        before = await snapshot_state()
        operation = ClientTemplateOperation(OperatorType.API)
        with pytest.raises(HTTPException) as exc_info:
            await operation.bulk_remove_client_templates(
                session,
                BulkClientTemplateSelection(ids={1}),
                SimpleNamespace(username="admin"),
            )

        assert exc_info.value.status_code == 409
        after = await snapshot_state()
        assert after == before

    await engine.dispose()


def test_xray_profile_uses_machine_tags_and_fallback_not_remarks():
    endpoints = [make_endpoint("primary", "de", remark="Berlin"), make_endpoint("fallback", "fi", remark="Helsinki")]

    config = build_xray_profile(profile(), endpoints)
    rendered = json.dumps(config)

    assert "Berlin" not in rendered
    assert "Helsinki" not in rendered
    assert "pg-proxy-" in rendered
    primary = next(item for item in config["routing"]["balancers"] if item["tag"] == "pg-auto-primary")
    assert primary["fallbackTag"].startswith("pg-proxy-")
    assert config["observatory"]["subjectSelector"] == [
        tag
        for balancer in config["routing"]["balancers"]
        if balancer["tag"].startswith("pg-auto-") and not balancer["tag"].startswith("pg-auto-country-")
        for tag in balancer["selector"]
    ]
    assert all(
        not outbound["tag"].startswith("pg-proxy-")
        for outbound in config["outbounds"]
        if outbound["tag"].startswith("pg-dialer-")
    )


def test_endpoint_tag_uses_stable_host_identity_not_selected_address():
    first = make_endpoint("primary", "de", host_id=55)
    first = endpoint_from_inbound(first.inbound, "first.example.test", first.settings)
    second = make_endpoint("primary", "de", host_id=55)
    second = endpoint_from_inbound(second.inbound, "second.example.test", second.settings)
    fallback = make_endpoint("fallback", "fi", host_id=56)

    first_tag = next(
        item["tag"]
        for item in build_xray_profile(profile(), [first, fallback])["outbounds"]
        if item["tag"].startswith("pg-proxy-")
    )
    second_tag = next(
        item["tag"]
        for item in build_xray_profile(profile(), [second, fallback])["outbounds"]
        if item["tag"].startswith("pg-proxy-")
    )

    assert first_tag == second_tag


def test_endpoint_tags_are_stable_for_multiple_inbounds_on_one_host():
    first = make_endpoint("primary", "de", host_id=1)
    second = make_endpoint("primary", "nl", host_id=1)

    assert build_xray_profile(profile(), [first, second]) == build_xray_profile(profile(), [second, first])


@pytest.mark.parametrize("builder", [build_xray_profile, build_singbox_profile])
def test_duplicate_endpoint_tags_are_stable_for_distinct_materialized_sources(builder):
    template = make_endpoint("primary", "de", host_id=71)
    first = endpoint_from_inbound(
        template.inbound,
        "alpha.example.test",
        {"id": "11111111-1111-1111-1111-111111111111"},
    )
    second = endpoint_from_inbound(
        template.inbound,
        "bravo.example.test",
        {"id": "22222222-2222-2222-2222-222222222222"},
    )

    config = builder(profile(), [first, second])
    reversed_config = builder(profile(), [second, first])

    assert first.machine_key == second.machine_key
    assert first.stable_tie_breaker != second.stable_tie_breaker
    assert config == reversed_config


def test_xray_retag_does_not_change_endpoint_data():
    outbounds = [
        {
            "tag": "proxy",
            "settings": {"servers": [{"address": "proxy", "password": "dialer"}]},
            "streamSettings": {
                "sockopt": {"dialerProxy": "dialer"},
                "xhttpSettings": {
                    "extra": {"downloadSettings": {"streamSettings": {"sockopt": {"dialerProxy": "dsdialer"}}}}
                },
            },
        },
        {"tag": "dialer", "protocol": "freedom"},
    ]

    retagged = _retag_xray_outbounds(
        outbounds,
        {"proxy": "pg-proxy-test", "dialer": "pg-dialer-test", "dsdialer": "pg-dsdialer-test"},
    )

    assert retagged[0]["tag"] == "pg-proxy-test"
    assert retagged[0]["streamSettings"]["sockopt"]["dialerProxy"] == "pg-dialer-test"
    assert (
        retagged[0]["streamSettings"]["xhttpSettings"]["extra"]["downloadSettings"]["streamSettings"]["sockopt"][
            "dialerProxy"
        ]
        == "pg-dsdialer-test"
    )
    assert retagged[0]["settings"]["servers"][0] == {"address": "proxy", "password": "dialer"}


def test_singbox_profile_keeps_pool_urltests_separate_and_excludes_manual_only_endpoints():
    endpoints = [
        make_endpoint("primary", "de"),
        make_endpoint("primary", "nl", exclude_from_auto=True),
        make_endpoint("fallback", "fi"),
    ]

    config = build_singbox_profile(profile(), endpoints)
    auto_primary = next(item for item in config["outbounds"] if item.get("tag") == "pg-auto-primary")
    primary_selector = next(item for item in config["outbounds"] if item.get("tag") == "pg-select-primary")

    assert auto_primary["type"] == "urltest"
    assert len(auto_primary["outbounds"]) == 1
    assert len(primary_selector["outbounds"]) == 3  # auto + both explicitly selectable endpoints
    assert {item["tag"] for item in config["outbounds"] if item.get("type") == "urltest"} == {
        "pg-auto-primary",
        "pg-auto-fallback",
        "pg-auto-country-de",
        "pg-auto-country-fi",
    }
    country_de = next(item for item in config["outbounds"] if item.get("tag") == "pg-country-de")
    assert country_de["outbounds"] == ["pg-auto-country-de", *auto_primary["outbounds"]]
    root = next(item for item in config["outbounds"] if item.get("tag") == "proxy")
    assert root["outbounds"].count("pg-select-primary") == 1


def test_xray_manual_only_endpoint_is_excluded_from_country_auto_and_observatory():
    automatic = make_endpoint("primary", "de", host_id=1)
    manual = make_endpoint("primary", "de", host_id=2, exclude_from_auto=True)

    config = build_xray_profile(profile(), [automatic, manual, make_endpoint("fallback", "fi", host_id=3)])
    automatic_tags = next(
        item["selector"] for item in config["routing"]["balancers"] if item["tag"] == "pg-auto-primary"
    )
    country_tags = next(item["selector"] for item in config["routing"]["balancers"] if item["tag"] == "pg-country-de")
    all_automatic_tags = {
        tag
        for item in config["routing"]["balancers"]
        if item["tag"].startswith("pg-auto-") and not item["tag"].startswith("pg-auto-country-")
        for tag in item["selector"]
    }
    manual_tags = {
        item["tag"]
        for item in config["outbounds"]
        if item.get("tag", "").startswith("pg-proxy-") and item["tag"] not in all_automatic_tags
    }

    assert country_tags == automatic_tags
    assert set(config["observatory"]["subjectSelector"]) == all_automatic_tags
    assert set(config["observatory"]["subjectSelector"]).isdisjoint(manual_tags)


def test_xray_observatory_selector_does_not_prefix_match_manual_duplicate():
    automatic = make_endpoint("primary", "de", host_id=1)
    manual = endpoint_from_inbound(
        automatic.inbound.model_copy(
            update={
                "profile_classification": {
                    "pool": "primary",
                    "country": "de",
                    "exclude_from_auto": True,
                }
            }
        ),
        automatic.address,
        automatic.settings,
    )

    config = build_xray_profile(profile(), [automatic, manual, make_endpoint("fallback", "fi", host_id=2)])
    reversed_config = build_xray_profile(profile(), [manual, automatic, make_endpoint("fallback", "fi", host_id=2)])
    selectors = config["observatory"]["subjectSelector"]
    all_proxy_tags = [
        outbound["tag"] for outbound in config["outbounds"] if outbound.get("tag", "").startswith("pg-proxy-")
    ]

    assert all(sum(tag.startswith(selector) for tag in all_proxy_tags) == 1 for selector in selectors)
    assert config == reversed_config


@pytest.mark.parametrize(
    "routing_rule, message",
    [
        (
            {"type": "field", "domain": ["example.com"], "outboundTag": "direct", "balancerTag": "pg-auto-primary"},
            "cannot set both",
        ),
        ({"type": "field", "domain": ["example.com"], "outboundTag": "missing"}, "unknown outbound"),
        ({"type": "field", "domain": ["example.com"], "balancerTag": "missing"}, "unknown balancer"),
    ],
)
def test_xray_profile_validates_generated_routing_targets(routing_rule, message):
    custom_profile = profile().model_copy(update={"routing_rules": [routing_rule]})

    with pytest.raises(ProfileValidationError, match=message):
        build_xray_profile(
            custom_profile,
            [make_endpoint("primary", "de"), make_endpoint("fallback", "fi", host_id=2)],
        )


def test_singbox_profile_validates_nested_logical_routing_targets():
    custom_profile = profile().model_copy(
        update={
            "routing_rules": [
                {
                    "type": "logical",
                    "mode": "or",
                    "outbound": "direct",
                    "rules": [{"domain_suffix": ["example.com"], "outbound": "missing"}],
                }
            ]
        }
    )

    with pytest.raises(ProfileValidationError, match=r"rules\[0\].outbound references unknown outbound"):
        build_singbox_profile(
            custom_profile,
            [make_endpoint("primary", "de"), make_endpoint("fallback", "fi", host_id=2)],
        )


def test_profile_omits_an_enabled_empty_secondary_pool():
    config = build_singbox_profile(profile(), [make_endpoint("primary", "de")])

    assert "pg-auto-fallback" not in {item.get("tag") for item in config["outbounds"]}


def test_profile_rejects_an_empty_default_pool():
    with pytest.raises(ProfileValidationError, match="default pool 'primary'"):
        build_xray_profile(profile(), [make_endpoint("fallback", "fi")])


@pytest.mark.parametrize("builder", [build_xray_profile, build_singbox_profile])
def test_profile_rejects_a_default_pool_with_only_manual_endpoints(builder):
    with pytest.raises(ProfileValidationError, match="no automatic endpoints in the default pool 'primary'"):
        builder(
            profile(),
            [
                make_endpoint("primary", "de", exclude_from_auto=True),
                make_endpoint("fallback", "fi", host_id=2),
            ],
        )


def test_xray_fallback_uses_highest_priority_automatic_endpoint():
    manual = make_endpoint("fallback", "us", host_id=2, exclude_from_auto=True, priority=0)
    preferred = make_endpoint("fallback", "fi", host_id=3, priority=10)
    lower_priority = make_endpoint("fallback", "nl", host_id=4, priority=20)

    config = build_xray_profile(
        profile(),
        [make_endpoint("primary", "de", host_id=1), lower_priority, manual, preferred],
    )
    primary = next(item for item in config["routing"]["balancers"] if item["tag"] == "pg-auto-primary")
    fallback_balancer = next(item for item in config["routing"]["balancers"] if item["tag"] == "pg-auto-fallback")

    assert len(fallback_balancer["selector"]) == 2
    assert primary["fallbackTag"] == fallback_balancer["selector"][0]


def test_profile_rejects_disabled_default_or_fallback_pool():
    with pytest.raises(ValueError, match="default_pool must reference an enabled pool"):
        SubscriptionProfile(default_pool="primary", pools=[ProfilePool(id="primary", enabled=False)])
    with pytest.raises(ValueError, match="fallback_pool 'fallback' must reference an enabled pool"):
        SubscriptionProfile(
            default_pool="primary",
            pools=[ProfilePool(id="primary", fallback_pool="fallback"), ProfilePool(id="fallback", enabled=False)],
        )


def test_profile_limits_pool_and_routing_rule_counts():
    with pytest.raises(ValueError):
        SubscriptionProfile(pools=[ProfilePool(id=f"pool-{index}") for index in range(65)])

    with pytest.raises(ValueError):
        SubscriptionProfile(routing_rules=[{} for _ in range(257)])


def test_disabled_pool_endpoints_are_not_exposed_by_country_selector():
    config = build_singbox_profile(
        SubscriptionProfile(
            default_pool="primary",
            pools=[ProfilePool(id="primary"), ProfilePool(id="disabled", enabled=False)],
        ),
        [make_endpoint("primary", "de", host_id=1), make_endpoint("disabled", "us", host_id=2)],
    )

    assert "pg-country-us" not in {item.get("tag") for item in config["outbounds"]}


def test_singbox_wireguard_is_kept_in_endpoints():
    inbound = SubscriptionInboundData(
        remark="WireGuard",
        host_id=77,
        inbound_tag="wireguard-primary",
        protocol="wireguard",
        address=["wg.example.test"],
        port=[51820],
        network="tcp",
        tls_config=TLSConfig(),
        transport_config=TCPTransportConfig(),
        wireguard_public_key="server-public-key",
        wireguard_allowed_ips=["0.0.0.0/0"],
        profile_classification={"pool": "primary", "country": "de"},
    )
    endpoint = endpoint_from_inbound(
        inbound, "wg.example.test", {"private_key": "private-key", "peer_ips": ["10.0.0.2/32"]}
    )
    fallback = make_endpoint("fallback", "fi", host_id=78)

    config = build_singbox_profile(profile(), [endpoint, fallback])

    assert config["endpoints"][0]["type"] == "wireguard"
    assert (
        config["endpoints"][0]["tag"]
        in next(item for item in config["outbounds"] if item.get("tag") == "pg-auto-primary")["outbounds"]
    )


def test_singbox_profile_assigns_distinct_stable_system_interfaces_to_wireguard_endpoints():
    endpoints = [make_wireguard_endpoint(host_id=201), make_wireguard_endpoint(host_id=202)]

    config = build_singbox_profile(profile(), endpoints)
    reversed_config = build_singbox_profile(profile(), list(reversed(endpoints)))

    names_by_tag = {endpoint["tag"]: endpoint["name"] for endpoint in config["endpoints"]}
    reversed_names_by_tag = {endpoint["tag"]: endpoint["name"] for endpoint in reversed_config["endpoints"]}
    assert names_by_tag == reversed_names_by_tag
    assert len(set(names_by_tag.values())) == 2
    assert all(name.startswith("wg") and len(name.encode()) <= 15 for name in names_by_tag.values())


class _CacheKV:
    def __init__(self, value=None):
        self.value = value
        self.written = None

    async def get(self, _key):
        return SimpleNamespace(value=self.value) if self.value is not None else None

    async def put(self, _key, value):
        self.written = value


@pytest.mark.asyncio
async def test_host_manager_rejects_markerless_pre_profile_cache():
    cached_host = make_endpoint("primary", "de", host_id=301).inbound.model_dump(mode="json")
    manager = HostManager()
    manager._kv = _CacheKV(json.dumps({"301": cached_host}).encode())

    assert await manager._load_state_from_cache() is False
    assert manager._hosts == {}


@pytest.mark.asyncio
async def test_host_manager_versioned_cache_round_trip_preserves_profile_identity():
    inbound = make_endpoint("primary", "de", host_id=302).inbound
    kv = _CacheKV()
    manager = HostManager()
    manager._kv = kv
    manager._hosts = {302: inbound}

    await manager._persist_state()
    persisted = json.loads(kv.written)
    assert persisted[manager.STATE_SCHEMA_KEY] == manager.STATE_SCHEMA_VERSION
    assert persisted["302"]["host_id"] == 302

    restored = HostManager()
    restored._kv = _CacheKV(kv.written)
    assert await restored._load_state_from_cache() is True
    assert restored._hosts[302].host_id == 302
    assert restored._hosts[302].profile_classification["pool"] == "primary"
    assert restored._hosts[302].profile_classification["country"] == "de"


@pytest.mark.parametrize("network", ["tcp", "ws", "grpc", "xhttp"])
def test_xray_profile_preserves_vless_transport_and_security(network):
    config = build_xray_profile(
        profile(),
        [make_vless_transport_endpoint(network, host_id=100), make_endpoint("fallback", "fi", host_id=101)],
    )
    outbound = next(
        item
        for item in config["outbounds"]
        if item.get("tag", "").startswith("pg-proxy-")
        and item["settings"]["vnext"][0]["address"] == "edge.example.test"
    )

    assert outbound["streamSettings"]["security"] == ("tls" if network == "ws" else "reality")
    assert outbound["streamSettings"]["network"] == network
    assert f"{network}Settings" in outbound["streamSettings"]


@pytest.mark.parametrize("network", ["tcp", "ws", "grpc"])
def test_singbox_profile_preserves_supported_vless_transport_and_security(network):
    config = build_singbox_profile(
        profile(),
        [make_vless_transport_endpoint(network, host_id=110), make_endpoint("fallback", "fi", host_id=111)],
    )
    outbound = next(
        item for item in config["outbounds"] if item.get("type") == "vless" and item["server"] == "edge.example.test"
    )

    if network == "ws":
        assert "reality" not in outbound["tls"]
    else:
        assert outbound["tls"]["reality"]["enabled"] is True
    if network == "tcp":
        assert "transport" not in outbound
    else:
        assert outbound["transport"]["type"] == network


def test_singbox_profile_rejects_xhttp_with_actionable_error():
    with pytest.raises(ProfileValidationError, match="unsupported by Sing-box profile output"):
        build_singbox_profile(
            profile(),
            [make_vless_transport_endpoint("xhttp", host_id=115), make_endpoint("fallback", "fi", host_id=116)],
        )


@pytest.mark.asyncio
async def test_legacy_subscription_generation_does_not_enter_profile_path(monkeypatch):
    async def templates():
        return {
            "USER_AGENT_TEMPLATE": "{}",
            "GRPC_USER_AGENT_TEMPLATE": "{}",
            "XRAY_SUBSCRIPTION_TEMPLATE": '{"outbounds": []}',
            "SINGBOX_SUBSCRIPTION_TEMPLATE": '{"inbounds": [], "outbounds": []}',
            "CLASH_SUBSCRIPTION_TEMPLATE": "{}",
        }

    async def xray_templates():
        return {}

    async def settings():
        return SimpleNamespace(custom_variables=[])

    async def legacy_output(*args, **kwargs):
        return "legacy-output-is-unchanged"

    def fail_if_profile_builder_is_called(*args, **kwargs):
        raise AssertionError("legacy generation must not enter the opt-in profile builder")

    monkeypatch.setattr("app.subscription.share.subscription_client_templates", templates)
    monkeypatch.setattr("app.subscription.share.subscription_xray_templates", xray_templates)
    monkeypatch.setattr("app.subscription.share.subscription_settings", settings)
    monkeypatch.setattr("app.subscription.share.get_effective_custom_variables", lambda *args: [])
    monkeypatch.setattr("app.subscription.share.setup_format_variables", lambda *args: {})
    monkeypatch.setattr("app.subscription.share.process_inbounds_and_tags", legacy_output)
    monkeypatch.setattr("app.subscription.share.build_xray_profile", fail_if_profile_builder_is_called)

    result = await generate_subscription(SimpleNamespace(), "xray", as_base64=False)

    assert result == "legacy-output-is-unchanged"


@pytest.mark.parametrize(
    ("user_agent", "profile_id"),
    [("Happ/3.8 Android", 41), ("Incy/1.2 iOS", 42), ("v2rayN/7.15", 43)],
)
def test_optional_client_rules_detect_profile_by_user_agent(user_agent, profile_id):
    rules = [
        SubRule(pattern=r"(?i)^happ", target=ConfigFormat.xray, profile_id=41),
        SubRule(pattern=r"(?i)^incy", target=ConfigFormat.xray, profile_id=42),
        SubRule(pattern=r"(?i)^v2rayn", target=ConfigFormat.xray, profile_id=43),
    ]

    matched = SubscriptionOperation.detect_client_rule(user_agent, rules)

    assert matched is not None
    assert matched.profile_id == profile_id


def test_profile_rule_rejects_non_json_target():
    with pytest.raises(ValueError, match="xray or sing_box"):
        SubRule(pattern=".*", target=ConfigFormat.clash, profile_id=41)


@pytest.mark.asyncio
async def test_profile_rule_selects_existing_client_template(monkeypatch):
    operator = SubscriptionOperation(OperatorType.API)
    selected_profile = SubscriptionProfile(client=ProfileClient.happ, happ_deeplink="happ://routing/add/e30=")
    fetch_profile = AsyncMock(
        return_value=("generated-profile", "application/json", ConfigFormat.xray, selected_profile)
    )
    monkeypatch.setattr(operator, "fetch_profile_config", fetch_profile)
    rule = SubRule(pattern=r"(?i)^happ", target=ConfigFormat.xray, profile_id=41)

    result = await operator.fetch_rule_config(None, SimpleNamespace(), rule)

    assert result == ("generated-profile", "application/json", ConfigFormat.xray, selected_profile)
    fetch_profile.assert_awaited_once_with(None, SimpleNamespace(), 41)


def test_happ_profile_emits_routing_metadata_only_when_selected():
    deeplink = "happ://routing/onadd/e30="
    happ_profile = SubscriptionProfile(client=ProfileClient.happ, happ_deeplink=deeplink)
    incy_profile = SubscriptionProfile(client=ProfileClient.incy)

    assert SubscriptionOperation.profile_response_headers(happ_profile) == {"routing": deeplink}
    assert SubscriptionOperation.profile_response_headers(incy_profile) == {}


def test_happ_deeplink_is_rejected_for_other_clients():
    with pytest.raises(ValueError, match="only supported for Happ"):
        SubscriptionProfile(client=ProfileClient.v2rayn, happ_deeplink="happ://routing/add/e30=")


def _run_profile_validator(binary_env: str, args: list[str], config: dict, tmp_path):
    binary = os.environ.get(binary_env)
    if not binary:
        pytest.skip(f"set {binary_env} to run the official client validator")
    config_path = tmp_path / "profile.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    result = subprocess.run([binary, *args, str(config_path)], capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def test_generated_xray_profile_passes_official_validator(tmp_path):
    config = build_xray_profile(
        profile(),
        [
            make_vless_transport_endpoint("tcp", host_id=120),
            make_vless_transport_endpoint("ws", host_id=121),
            make_vless_transport_endpoint("grpc", host_id=122),
            make_vless_transport_endpoint("xhttp", host_id=123),
            make_wireguard_endpoint(host_id=124),
            make_endpoint("fallback", "fi", host_id=125),
        ],
    )
    _run_profile_validator("XRAY_BINARY", ["run", "-test", "-config"], config, tmp_path)


def test_generated_singbox_profile_passes_official_validator(tmp_path):
    config = build_singbox_profile(
        profile(),
        [
            make_vless_transport_endpoint("tcp", host_id=130),
            make_vless_transport_endpoint("ws", host_id=131),
            make_vless_transport_endpoint("grpc", host_id=132),
            make_wireguard_endpoint(host_id=133),
            make_endpoint("fallback", "fi", host_id=134),
        ],
    )
    _run_profile_validator("SING_BOX_BINARY", ["check", "-c"], config, tmp_path)
