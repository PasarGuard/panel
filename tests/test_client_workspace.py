import asyncio
import base64
import json
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.crud.client_template import get_client_template_by_id, get_client_templates
from app.db.crud.settings import get_settings
from app.db.models import ClientTemplate, Settings
from app.models.client_template import BulkClientTemplateSelection, ClientTemplateListQuery, ClientTemplateModify
from app.models.client_workspace import ClientWorkspaceApply, ClientWorkspacePreview
from app.models.settings import SettingsModify, SubRule
from app.operation import OperatorType, client_workspace as workspace_module
from app.operation.client_template import ClientTemplateOperation
from app.operation.client_workspace import ClientWorkspaceOperation
from app.operation.settings import SettingsOperation
from app.operation.subscription import SubscriptionOperation
from app.subscription.client_diagnostics import diagnose_client_body
from app.subscription.happ import happ_deeplink, load_happ_document
from app.subscription.singbox import SingBoxConfiguration


@pytest_asyncio.fixture
async def workspace_db(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'workspace.db').as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: Settings.__table__.create(sync))
        await connection.run_sync(lambda sync: ClientTemplate.__table__.create(sync))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        session.add(
            Settings(
                telegram={}, webhook={}, notification_settings={}, notification_enable={},
                subscription={"rules": []}, hwid={}, general={},
            )
        )
        await session.commit()
    monkeypatch.setattr(workspace_module, "refresh_client_templates_cache", AsyncMock())
    monkeypatch.setattr(workspace_module, "refresh_caches", AsyncMock())
    monkeypatch.setattr(workspace_module.router, "publish", AsyncMock())
    yield sessions
    await engine.dispose()


def draft(revision, **overrides):
    data = {
        "expected_revision": revision,
        "template": {
            "name": "Operator label", "template_type": "happ_routing",
            "content": '{"Name":"Имя клиента","DirectSites":["example.org"],"Future":{"v":1}}',
        },
        "rules": [{
            "pattern": "^Happ", "target": "links", "ui_application": "Happ",
            "happ_routing": {"transport": "body", "action": "onadd", "enabled": None},
        }],
        "bind_rule_indices": [0],
    }
    return ClientWorkspaceApply.model_validate({**data, **overrides})


@pytest.mark.asyncio
async def test_workspace_revision_queries_compile_as_mysql_current_locking_reads():
    from sqlalchemy.dialects import mysql

    settings_db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None))
    )
    await get_settings(settings_db, for_update=True)
    settings_stmt = settings_db.execute.await_args.args[0]
    assert "FOR UPDATE" in str(settings_stmt.compile(dialect=mysql.dialect()))
    assert settings_stmt.get_execution_options()["populate_existing"] is True

    template_db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(scalar=lambda: 0),
                SimpleNamespace(scalars=lambda: SimpleNamespace(all=list)),
            ]
        )
    )
    await get_client_templates(template_db, ClientTemplateListQuery(), for_update=True)
    template_stmt = template_db.execute.await_args_list[1].args[0]
    assert "FOR UPDATE" in str(template_stmt.compile(dialect=mysql.dialect()))
    assert template_stmt.get_execution_options()["populate_existing"] is True

    by_id_db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(unique=lambda: SimpleNamespace(scalar_one_or_none=lambda: None)))
    )
    await get_client_template_by_id(by_id_db, 7, for_update=True)
    by_id_stmt = by_id_db.execute.await_args.args[0]
    assert "FOR UPDATE" in str(by_id_stmt.compile(dialect=mysql.dialect()))
    assert by_id_stmt.get_execution_options()["populate_existing"] is True


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("CLIENT_WORKSPACE_MYSQL_TEST_URL"), reason="isolated MySQL URL not configured")
async def test_mysql_repeatable_read_stale_identity_map_cannot_overwrite_concurrent_template(monkeypatch):
    """The configured database is exclusive to this test; its two owned tables are recreated and removed."""
    engine = create_async_engine(os.environ["CLIENT_WORKSPACE_MYSQL_TEST_URL"], isolation_level="REPEATABLE READ")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    workspace = ClientWorkspaceOperation(OperatorType.API)
    ordinary = ClientTemplateOperation(OperatorType.API)
    monkeypatch.setattr(ordinary, "_sync_client_template_cache", AsyncMock())

    original_content = '{"inbounds":[{}],"outbounds":[{"protocol":"freedom","tag":"direct"}],"marker":"old"}'
    writer_content = '{"inbounds":[{}],"outbounds":[{"protocol":"freedom","tag":"direct"}],"marker":"writer"}'
    try:
        async with engine.begin() as connection:
            await connection.run_sync(lambda sync: ClientTemplate.__table__.drop(sync, checkfirst=True))
            await connection.run_sync(lambda sync: Settings.__table__.drop(sync, checkfirst=True))
            await connection.run_sync(lambda sync: Settings.__table__.create(sync))
            await connection.run_sync(lambda sync: ClientTemplate.__table__.create(sync))
        async with sessions() as seed:
            seed.add(
                Settings(
                    telegram={}, webhook={"timeout": 1, "recurrent": 1},
                    notification_settings={"max_retries": 2}, notification_enable={},
                    subscription={"rules": []}, hwid={}, general={},
                )
            )
            template = ClientTemplate(
                name="default", template_type="xray_subscription",
                content=original_content, is_default=True, is_system=False,
            )
            seed.add(template)
            profile = ClientTemplate(
                name="profile",
                template_type="xray_profile",
                content='{"default_pool":"primary","pools":[{"id":"primary"}]}',
                is_default=False,
                is_system=False,
            )
            seed.add(profile)
            await seed.flush()
            template_id = template.id
            profile_id = profile.id
            await seed.commit()
        async with sessions() as initial:
            old_revision = (await workspace.workspace(initial)).revision
            await initial.rollback()

        async with sessions() as stale:
            # Plain reads model an authentication/data lookup that establishes an
            # old REPEATABLE READ snapshot and populates the ORM identity map.
            assert (await get_settings(stale)).subscription == {"rules": []}
            templates, _ = await get_client_templates(stale, ClientTemplateListQuery())
            assert templates[0].content == original_content

            async with sessions() as writer:
                await ordinary.modify_client_template(
                    writer,
                    template_id,
                    ClientTemplateModify(content=writer_content),
                    SimpleNamespace(username="writer"),
                )

            still_stale, _ = await get_client_templates(stale, ClientTemplateListQuery())
            assert still_stale[0].content == original_content

            with pytest.raises(HTTPException) as exc:
                await workspace.apply(
                    stale,
                    ClientWorkspaceApply(expected_revision=old_revision, template=None, rules=[]),
                )
            assert exc.value.status_code == 409

        async with sessions() as verify:
            stored = await ordinary._get_locked_client_template(verify, template_id)
            assert stored.content == writer_content
            await verify.rollback()

        async with sessions() as stale_reference:
            assert (await get_settings(stale_reference)).subscription == {"rules": []}
            await get_client_template_by_id(stale_reference, profile_id)
            async with sessions() as writer:
                settings = await get_settings(writer)
                settings.subscription = {
                    "rules": [{"pattern": ".*", "target": "xray", "profile_id": profile_id}]
                }
                await writer.commit()

            with pytest.raises(HTTPException) as exc:
                await ordinary.remove_client_template(
                    stale_reference,
                    profile_id,
                    SimpleNamespace(username="deleter"),
                )
            assert exc.value.status_code == 409
            assert "referenced by settings rules" in exc.value.detail
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(lambda sync: ClientTemplate.__table__.drop(sync, checkfirst=True))
            await connection.run_sync(lambda sync: Settings.__table__.drop(sync, checkfirst=True))
        await engine.dispose()


@pytest.mark.asyncio
async def test_atomic_create_bind_and_stale_revision_rolls_back(workspace_db):
    operation = ClientWorkspaceOperation(OperatorType.API)
    async with workspace_db() as db:
        initial = await operation.workspace(db)
        saved = await operation.apply(db, draft(initial.revision))
        assert saved.subscription.rules[0].happ_routing.template_id == saved.templates[0].id
        assert saved.subscription.rules[0].ui_application == "Happ"
        assert not saved.templates[0].is_default
        assert load_happ_document(saved.templates[0].content)["Name"] == "Имя клиента"
        with pytest.raises(HTTPException) as exc:
            await operation.apply(db, draft(initial.revision, rules=[]))
        assert exc.value.status_code == 409
        assert (await operation.workspace(db)) == saved


@pytest.mark.asyncio
async def test_atomic_generator_create_bind_and_preview(workspace_db, monkeypatch):
    operation = ClientWorkspaceOperation(OperatorType.API)
    monkeypatch.setattr(SubscriptionOperation, "get_validated_user_by_id", AsyncMock(return_value=object()))
    monkeypatch.setattr(
        SubscriptionOperation,
        "validated_user",
        AsyncMock(return_value=SimpleNamespace(status="active")),
    )
    monkeypatch.setattr(SubscriptionOperation, "_render_profile_config", AsyncMock(return_value='{"outbounds":[]}'))
    monkeypatch.setattr(SubscriptionOperation, "_get_rule_response_header_variables", AsyncMock(return_value={}))
    request_data = {
        "template": {
            "name": "Generated Xray",
            "template_type": "xray_profile",
            "content": '{"default_pool":"primary","pools":[{"id":"primary"}]}',
        },
        "rules": [{"pattern": ".*", "target": "xray", "template_id": 999}],
        "bind_rule_indices": [0],
    }
    async with workspace_db() as db:
        initial = await operation.workspace(db)
        preview_request = ClientWorkspacePreview(
            expected_revision=initial.revision,
            user_id=7,
            user_agent="Generator client",
            **request_data,
        )
        preview = await operation.preview(db, preview_request, SimpleNamespace())
        assert preview["matched_rule"]["profile_id"] == preview["source"]["id"]
        assert preview["source"]["kind"] == "subscription_profile"
        assert preview["content"] == '{"outbounds":[]}'
        saved = await operation.apply(
            db,
            ClientWorkspaceApply(expected_revision=initial.revision, **request_data),
        )
        assert saved.subscription.rules[0].profile_id == saved.templates[0].id
        assert saved.subscription.rules[0].template_id is None


@pytest.mark.asyncio
async def test_parallel_workspace_saves_cannot_overwrite(workspace_db):
    operation = ClientWorkspaceOperation(OperatorType.API)
    async with workspace_db() as db:
        revision = (await operation.workspace(db)).revision

    async def save():
        async with workspace_db() as db:
            try:
                return await operation.apply(db, draft(revision))
            except HTTPException as exc:
                return exc.status_code

    results = await asyncio.gather(save(), save())
    assert sum(result == 409 for result in results) == 1


@pytest.mark.asyncio
async def test_ordinary_template_mutation_invalidates_workspace_revision(workspace_db, monkeypatch):
    workspace = ClientWorkspaceOperation(OperatorType.API)
    ordinary = ClientTemplateOperation(OperatorType.API)
    monkeypatch.setattr(ordinary, "_sync_client_template_cache", AsyncMock())
    async with workspace_db() as db:
        initial = await workspace.workspace(db)
        await ordinary.create_client_template(
            db,
            draft(initial.revision).template,
            SimpleNamespace(username="admin"),
        )
        with pytest.raises(HTTPException) as exc:
            await workspace.apply(db, draft(initial.revision, template=None, bind_rule_indices=[]))
        assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_invalid_python_regex_is_rejected_before_write(workspace_db):
    operation = ClientWorkspaceOperation(OperatorType.API)
    async with workspace_db() as db:
        initial = await operation.workspace(db)
        request = draft(initial.revision)
        request.rules[0]["pattern"] = "["
        with pytest.raises(HTTPException) as exc:
            await operation.apply(db, request)
        assert exc.value.status_code == 400
        assert "rule 0" in exc.value.detail
        assert await operation.workspace(db) == initial


@pytest.mark.asyncio
async def test_post_commit_cache_failure_returns_saved_snapshot_with_warning(workspace_db, monkeypatch):
    operation = ClientWorkspaceOperation(OperatorType.API)
    monkeypatch.setattr(
        workspace_module,
        "refresh_client_templates_cache",
        AsyncMock(side_effect=RuntimeError("cache failed")),
    )
    async with workspace_db() as db:
        initial = await operation.workspace(db)
        saved = await operation.apply(db, draft(initial.revision))
        assert saved.sync_warning == "cache_refresh_failed"
        persisted = await operation.workspace(db)
        assert persisted.revision == saved.revision
        assert persisted.subscription == saved.subscription


@pytest.mark.asyncio
async def test_referenced_happ_blocks_single_and_bulk_delete(workspace_db):
    workspace = ClientWorkspaceOperation(OperatorType.API)
    ordinary = ClientTemplateOperation(OperatorType.API)
    async with workspace_db() as db:
        initial = await workspace.workspace(db)
        request = draft(initial.revision)
        request.rules[0]["happ_routing"]["transport"] = "header"
        saved = await workspace.apply(db, request)
        template_id = saved.templates[0].id
        with pytest.raises(HTTPException) as exc:
            await ordinary.modify_client_template(
                db,
                template_id,
                ClientTemplateModify(content=json.dumps({"Name": "x" * 3000})),
                SimpleNamespace(username="admin"),
            )
        assert exc.value.status_code == 400
        for bulk in (False, True):
            with pytest.raises(HTTPException) as exc:
                if bulk:
                    await ordinary.bulk_remove_client_templates(
                        db, BulkClientTemplateSelection(ids={template_id}), SimpleNamespace(username="admin")
                    )
                else:
                    await ordinary.remove_client_template(db, template_id, SimpleNamespace(username="admin"))
            assert exc.value.status_code == 409


@pytest.mark.parametrize(
    "rule",
    [
        {"target": "links", "template_id": 1},
        {"target": "xray", "profile_id": 1, "template_id": 2},
        {"target": "xray", "profile_id": 1, "happ_routing": {"template_id": 2}},
        {"target": "xray", "happ_routing": {"template_id": 1}},
        {"target": "links_base64", "happ_routing": {"template_id": 1, "transport": "body"}},
        {"target": "links", "happ_routing": {"template_id": 1}, "response_headers": {"Routing": "x"}},
    ],
)
def test_invalid_binding_combinations_rejected(rule):
    with pytest.raises(ValidationError):
        SubRule.model_validate({"pattern": ".*", **rule})


def test_happ_unicode_roundtrip_and_header_limit():
    source = {"Name": "Маршруты", "Unknown": {"x": [1, True]}}
    link, decoded = happ_deeplink(json.dumps(source), "onadd", "header")
    assert decoded == source
    assert json.loads(base64.b64decode(link.split("/")[-1])) == source
    with pytest.raises(ValueError, match="2048"):
        happ_deeplink(json.dumps({"Name": "я" * 1000}), "add", "header")
    assert happ_deeplink(json.dumps({"Name": "я" * 1000}), "add", "body")[0]


@pytest.mark.asyncio
async def test_draft_preview_has_no_hwid_or_activity_writes(workspace_db, monkeypatch):
    operation = ClientWorkspaceOperation(OperatorType.API)
    monkeypatch.setattr(SubscriptionOperation, "get_validated_user_by_id", AsyncMock(return_value=object()))
    monkeypatch.setattr(SubscriptionOperation, "validated_user", AsyncMock(return_value=SimpleNamespace(status="active")))
    monkeypatch.setattr(SubscriptionOperation, "_get_rule_response_header_variables", AsyncMock(return_value={}))
    monkeypatch.setattr(SubscriptionOperation, "fetch_config", AsyncMock(return_value=("ss://server", "text/plain")))
    hwid = AsyncMock()
    update = AsyncMock()
    monkeypatch.setattr(SubscriptionOperation, "validate_and_register_hwid", hwid)
    monkeypatch.setattr("app.operation.subscription.user_sub_update", update)
    async with workspace_db() as db:
        initial = await operation.workspace(db)
        request = ClientWorkspacePreview(**draft(initial.revision).model_dump(), user_id=7, user_agent="Happ/1")
        preview = await operation.preview(db, request, SimpleNamespace())
        assert preview["happ"]["decoded"]["Name"] == "Имя клиента"
        assert "happ://routing/onadd/" in preview["content"]
        assert await operation.workspace(db) == initial
    hwid.assert_not_awaited()
    update.assert_not_awaited()


@pytest.mark.asyncio
async def test_partial_settings_edit_preserves_workspace_rules(workspace_db, monkeypatch):
    operation = SettingsOperation(OperatorType.API)
    monkeypatch.setattr("app.operation.settings.refresh_caches", AsyncMock())
    monkeypatch.setattr("app.operation.settings.router.publish", AsyncMock())
    monkeypatch.setattr(operation, "reset_services", AsyncMock())
    async with workspace_db() as db:
        settings = (await db.execute(select(Settings))).scalar_one()
        settings.webhook = {"timeout": 1, "recurrent": 1}
        settings.notification_settings = {"max_retries": 2}
        settings.subscription = {
            "rules": [{"pattern": "^Happ", "target": "links", "ui_application": "Happ"}],
            "profile_title": "Keep", "support_url": "https://example.org/help",
        }
        await db.commit()
        saved = await operation.modify_settings(db, SettingsModify(subscription={"announce": "Changed"}))
        assert saved.subscription.rules[0].ui_application == "Happ"
        assert saved.subscription.profile_title == "Keep"
        assert saved.subscription.announce == "Changed"


@pytest.mark.asyncio
async def test_settings_update_rejects_missing_native_reference(workspace_db):
    operation = SettingsOperation(OperatorType.API)
    async with workspace_db() as db:
        before = await operation.get_settings(db)
        before.webhook = {"timeout": 1, "recurrent": 1}
        before.notification_settings = {"max_retries": 2}
        await db.commit()
        before_subscription = dict(before.subscription)
        with pytest.raises(HTTPException) as exc:
            await operation.modify_settings(
                db,
                SettingsModify(subscription={"rules": [{"pattern": ".*", "target": "xray", "template_id": 999}]}),
            )
        assert exc.value.status_code == 400
        await db.rollback()
        assert (await operation.get_settings(db)).subscription == before_subscription


@pytest.mark.asyncio
async def test_preloaded_settings_cannot_hide_new_profile_reference_on_delete(workspace_db):
    ordinary = ClientTemplateOperation(OperatorType.API)
    async with workspace_db() as seed:
        profile = ClientTemplate(
            name="profile",
            template_type="xray_profile",
            content='{"default_pool":"primary","pools":[{"id":"primary"}]}',
            is_default=False,
            is_system=False,
        )
        seed.add(profile)
        await seed.commit()
        profile_id = profile.id

    async with workspace_db() as stale:
        assert (await get_settings(stale)).subscription == {"rules": []}
        async with workspace_db() as writer:
            settings = await get_settings(writer)
            settings.subscription = {
                "rules": [{"pattern": ".*", "target": "xray", "profile_id": profile_id}]
            }
            await writer.commit()

        for bulk in (False, True):
            with pytest.raises(HTTPException) as exc:
                if bulk:
                    await ordinary.bulk_remove_client_templates(
                        stale,
                        BulkClientTemplateSelection(ids={profile_id}),
                        SimpleNamespace(username="admin"),
                    )
                else:
                    await ordinary.remove_client_template(
                        stale, profile_id, SimpleNamespace(username="admin")
                    )
            assert exc.value.status_code == 409
            assert "referenced by settings rules" in exc.value.detail


@pytest.mark.asyncio
async def test_workspace_routes_enforce_each_required_permission(monkeypatch):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.db import get_db
    from app.models.admin import AdminDetails, AdminRoleData
    from app.models.admin_role import RolePermissions
    from app.routers.authentication import get_current
    from app.routers.client_template import router, workspace_operator

    application = FastAPI()
    application.include_router(router)
    admin = AdminDetails(
        username="reader",
        role=AdminRoleData(
            permissions=RolePermissions(
                settings={"read": True, "update": True},
                client_templates={"read": True},
            )
        ),
    )
    application.dependency_overrides[get_current] = lambda: admin
    application.dependency_overrides[get_db] = lambda: None
    apply = AsyncMock()
    preview = AsyncMock()
    monkeypatch.setattr(workspace_operator, "apply", apply)
    monkeypatch.setattr(workspace_operator, "preview", preview)
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
        response = await client.post("/api/client_template/apply", json=draft("revision").model_dump())
        assert response.status_code == 403
        assert "client_templates.create" in response.json()["detail"]
        response = await client.post(
            "/api/client_template/preview",
            json={**draft("revision").model_dump(), "user_id": 1, "user_agent": "Happ"},
        )
        assert response.status_code == 403
        assert "users.read" in response.json()["detail"]
    apply.assert_not_awaited()
    preview.assert_not_awaited()


def test_singbox_preserves_explicit_groups_only_for_native_document():
    legacy = SingBoxConfiguration(
        singbox_template_content=json.dumps({
            "outbounds": [
                {"type": "vless", "tag": "server"},
                {"type": "selector", "tag": "manual", "outbounds": ["fixed"]},
                {"type": "urltest", "tag": "auto", "outbounds": []},
            ]
        }),
    )
    legacy._finalize_config()
    assert legacy.config["outbounds"][1]["outbounds"] == ["server", "auto"]

    native = SingBoxConfiguration(
        singbox_template_content=json.dumps({
            "outbounds": [
                {"type": "vless", "tag": "server"},
                {"type": "selector", "tag": "manual", "outbounds": ["fixed"]},
                {"type": "urltest", "tag": "auto", "outbounds": []},
            ]
        }),
        preserve_authored_groups=True,
    )
    native._finalize_config()
    assert native.config["outbounds"][1]["outbounds"] == ["fixed"]
    assert native.config["outbounds"][2]["outbounds"] == ["server"]

    empty = SingBoxConfiguration(singbox_template_content='{"outbounds":[{"type":"selector","tag":"auto","outbounds":[]}]}')
    empty._finalize_config()
    assert empty.config["outbounds"][0]["outbounds"] == []
    assert diagnose_client_body(empty.render(), "sing_box") == [
        "outbounds[0].outbounds has no selectable targets."
    ]


@pytest.mark.asyncio
async def test_native_rule_checks_type_before_generation(monkeypatch):
    operation = SubscriptionOperation(OperatorType.API)
    generate = AsyncMock(return_value=("native", "application/json"))
    monkeypatch.setattr(operation, "fetch_config", generate)
    rule = SubRule(pattern=".*", target="xray", template_id=3)
    templates = {3: SimpleNamespace(template_type="singbox_subscription", content="{}")}
    with pytest.raises(HTTPException) as exc:
        await operation.fetch_rule_config(None, SimpleNamespace(), rule, templates)
    assert exc.value.status_code == 422
    generate.assert_not_awaited()
    templates[3].template_type = "xray_subscription"
    assert (await operation.fetch_rule_config(None, SimpleNamespace(), rule, templates))[0] == "native"
    assert generate.await_args.args[-1] == ("XRAY_SUBSCRIPTION_TEMPLATE", "{}")


@pytest.mark.asyncio
async def test_parallel_native_xray_templates_do_not_mutate_cache_or_load_host_overrides(monkeypatch):
    from app.subscription.share import generate_subscription

    cached = {
        "XRAY_SUBSCRIPTION_TEMPLATE": '{"outbounds":[],"marker":"default"}',
        "USER_AGENT_TEMPLATE": '{"list":["UA"]}',
        "GRPC_USER_AGENT_TEMPLATE": '{"list":["grpc"]}',
    }
    original = dict(cached)
    monkeypatch.setattr("app.subscription.share.subscription_client_templates", AsyncMock(return_value=cached))
    host_overrides = AsyncMock(return_value={99: "host"})
    monkeypatch.setattr("app.subscription.share.subscription_xray_templates", host_overrides)
    reached = 0
    both_started = asyncio.Event()

    async def render(user, variables, conf, client_templates, **kwargs):
        nonlocal reached
        assert kwargs["xray_template_overrides"] is None
        reached += 1
        if reached == 2:
            both_started.set()
        await both_started.wait()
        return conf.template["marker"]

    monkeypatch.setattr("app.subscription.share.process_inbounds_and_tags", render)
    monkeypatch.setattr("app.subscription.share.subscription_settings", AsyncMock(return_value=SimpleNamespace(custom_variables=[])))
    monkeypatch.setattr("app.subscription.share.setup_format_variables", lambda *_: {})
    user = SimpleNamespace(admin=None)
    outputs = await asyncio.gather(*[
        generate_subscription(
            user, "xray", False,
            native_template=("XRAY_SUBSCRIPTION_TEMPLATE", json.dumps({"outbounds": [], "marker": marker})),
        )
        for marker in ("first", "second")
    ])
    assert outputs == ["first", "second"]
    assert cached == original
    host_overrides.assert_not_awaited()
