"""Atomic client-template and subscription-rule workspace operations."""

import hashlib
import json
import re
from copy import deepcopy
from types import SimpleNamespace

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.db.crud.client_template import (
    TEMPLATE_TYPE_TO_LEGACY_KEY,
    create_client_template,
    get_client_templates,
    modify_client_template,
)
from app.db.crud.settings import get_settings, lock_settings_row
from app.models.client_template import (
    ClientTemplateListQuery,
    ClientTemplateModify,
    ClientTemplateResponse,
    ClientTemplateType,
)
from app.models.client_workspace import ClientWorkspaceResponse
from app.models.settings import NATIVE_TEMPLATE_BY_TARGET, Subscription
from app.nats.message import MessageTopic
from app.nats.router import router
from app.operation.client_template import EXPLICIT_TEMPLATE_TYPES, ClientTemplateOperation
from app.operation.settings import SettingsOperation
from app.operation.subscription import SubscriptionOperation
from app.settings import refresh_caches
from app.subscription.client_templates import refresh_client_templates_cache
from app.subscription.happ import happ_deeplink
from app.utils.logger import get_logger

logger = get_logger("client-workspace-operation")


class ClientWorkspaceOperation(ClientTemplateOperation):
    async def workspace(self, db):
        # Locking reads are current reads under MySQL/MariaDB REPEATABLE READ,
        # even when authentication already established a transaction snapshot.
        settings = await get_settings(db, for_update=True)
        templates, _ = await get_client_templates(db, ClientTemplateListQuery(), for_update=True)
        result = ClientWorkspaceResponse(
            revision="pending",
            subscription=Subscription.model_validate(settings.subscription),
            templates=[ClientTemplateResponse.model_validate(template) for template in templates],
        )
        canonical = result.model_dump(mode="json", exclude={"revision", "sync_warning"})
        result.revision = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return result

    async def check_revision(self, db, expected):
        snapshot = await self.workspace(db)
        if snapshot.revision != expected:
            await self.raise_error("Workspace changed; reload before applying", 409, db=db)
        return snapshot

    async def validate_draft(self, db, draft):
        if draft is None:
            return None
        await self._validate_template_content(draft.template_type, draft.content)
        if draft.template_type in EXPLICIT_TEMPLATE_TYPES and draft.is_default:
            await self.raise_error("Explicit templates cannot be set as default", 400)
        existing = None
        if draft.id is not None:
            existing = await self._get_locked_client_template(db, draft.id)
            if ClientTemplateType(existing.template_type) != draft.template_type:
                await self.raise_error("Template type cannot be changed", 400)
            if (
                existing.is_default
                and not draft.is_default
                and draft.template_type not in EXPLICIT_TEMPLATE_TYPES
            ):
                await self.raise_error("Set another template as default before unsetting this default", 400)
        return existing

    async def bound_subscription(self, snapshot, request, template_id):
        rules = deepcopy(request.rules)
        for index, rule in enumerate(rules):
            try:
                re.compile(rule.get("pattern", ""))
            except (TypeError, re.error):
                await self.raise_error(f"Subscription rule {index} has an invalid Python regular expression", 400)
        if request.bind_rule_indices and request.template is None:
            await self.raise_error("Binding indices require a template draft", 400)
        for index in request.bind_rule_indices:
            if index < 0 or index >= len(rules):
                await self.raise_error("Rule binding index is out of range", 400)
            rule = rules[index]
            if request.template.template_type == ClientTemplateType.happ_routing:
                binding = rule.get("happ_routing")
                if not isinstance(binding, dict):
                    await self.raise_error("Happ binding requires transport, action and enabled options", 400)
                binding["template_id"] = template_id
            else:
                rule["template_id"] = template_id
        try:
            return Subscription.model_validate({**snapshot.subscription.model_dump(), "rules": rules})
        except ValidationError as exc:
            await self.raise_error(
                "Invalid subscription rules: " + "; ".join(error["msg"] for error in exc.errors()), 400
            )

    async def apply(self, db, request):
        try:
            settings = await lock_settings_row(db)
            snapshot = await self.check_revision(db, request.expected_revision)
            existing = await self.validate_draft(db, request.template)
            saved = None
            if request.template is not None:
                if existing is None:
                    saved = await create_client_template(db, request.template, commit=False)
                else:
                    saved = await modify_client_template(
                        db,
                        existing,
                        ClientTemplateModify(**request.template.model_dump(exclude={"id", "template_type"})),
                        commit=False,
                    )
            subscription = await self.bound_subscription(snapshot, request, saved.id if saved else None)
            await SettingsOperation(self.operator_type)._validate_subscription_template_rules(db, subscription)
            settings.subscription = subscription.model_dump(mode="json")
            await db.flush()
            result = await self.workspace(db)
            await db.commit()
        except IntegrityError:
            await db.rollback()
            await self.raise_error("Template with this name already exists for this type", 409)
        except BaseException:
            await db.rollback()
            raise

        await refresh_client_templates_cache()
        await refresh_caches()
        for topic in (MessageTopic.CLIENT_TEMPLATE, MessageTopic.SETTING):
            try:
                await router.publish(topic, {"action": "refresh"})
            except Exception:
                result.sync_warning = "worker_notification_failed"
                logger.warning("Workspace saved; worker cache notification failed for topic %s", topic)
        return result

    async def preview(self, db, request, admin):
        snapshot = await self.check_revision(db, request.expected_revision)
        await self.validate_draft(db, request.template)
        overrides = {}
        template_id = None
        if request.template is not None:
            template_id = request.template.id or max((template.id for template in snapshot.templates), default=0) + 1
            overrides[template_id] = SimpleNamespace(**{**request.template.model_dump(), "id": template_id})
        subscription = await self.bound_subscription(snapshot, request, template_id)
        by_id = {template.id: template for template in snapshot.templates}
        if request.template is not None:
            draft = overrides[template_id]
            same_type = [template for template in by_id.values() if template.template_type == draft.template_type]
            if not same_type and draft.template_type in TEMPLATE_TYPE_TO_LEGACY_KEY:
                draft.is_default = True
            if draft.is_default:
                by_id = {
                    key: template.model_copy(update={"is_default": False})
                    if template.template_type == draft.template_type
                    else template
                    for key, template in by_id.items()
                }
        by_id.update(overrides)
        for rule in subscription.rules:
            references = [(rule.template_id, NATIVE_TEMPLATE_BY_TARGET.get(rule.target))]
            if rule.happ_routing:
                references.append((rule.happ_routing.template_id, ClientTemplateType.happ_routing))
            for reference, expected in references:
                if reference is not None and (
                    reference not in by_id or ClientTemplateType(by_id[reference].template_type) != expected
                ):
                    await self.raise_error("Referenced client template missing or incompatible", 400)
            if rule.happ_routing:
                try:
                    happ_deeplink(
                        by_id[rule.happ_routing.template_id].content,
                        rule.happ_routing.action,
                        rule.happ_routing.transport,
                    )
                except ValueError as exc:
                    await self.raise_error(str(exc), 400)
        return await SubscriptionOperation(self.operator_type).user_subscription_rule_preview_by_id(
            db,
            request.user_id,
            admin,
            request.user_agent,
            subscription,
            by_id,
        )
