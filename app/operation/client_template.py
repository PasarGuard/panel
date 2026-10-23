import json
import traceback
from collections.abc import Iterable

import yaml
from jinja2 import TemplateSyntaxError
from jinja2.sandbox import SecurityError
from sqlalchemy.exc import IntegrityError

from app.core.hosts import host_manager
from app.db import AsyncSession
from app.db.crud.client_template import (
    clear_host_subscription_template_overrides,
    count_client_templates_by_type,
    create_client_template,
    get_client_templates,
    get_client_templates_simple,
    get_first_template_by_type,
    modify_client_template,
    remove_client_template,
    remove_client_templates,
    set_default_template,
)
from app.models.admin import AdminDetails
from app.models.client_template import (
    BulkClientTemplateSelection,
    ClientTemplateCreate,
    ClientTemplateListQuery,
    ClientTemplateModify,
    ClientTemplateResponse,
    ClientTemplateResponseList,
    ClientTemplateSimple,
    ClientTemplateSimpleListQuery,
    ClientTemplatesSimpleResponse,
    ClientTemplateType,
    ClientTemplateValidation,
    RemoveClientTemplatesResponse,
    effective_use_jinja,
)
from app.nats.message import MessageTopic
from app.nats.router import router
from app.settings import subscription_settings
from app.subscription.client_templates import refresh_client_templates_cache
from app.subscription.host_refs import sample_host_refs
from app.templates import compile_template, render_compiled
from app.templates.pool import TemplatesBusy, validation_pool
from app.templates.variables import REQUEST_VARIABLES, SAMPLE_FORMAT_VARIABLES, UNLIMITED_FORMAT_VARIABLES
from app.utils.logger import get_logger

from . import BaseOperation

logger = get_logger("client-template-operation")


# Validation renders with twice the hosts the panel has, within these bounds
MIN_SAMPLE_HOSTS = 100
MAX_SAMPLE_HOSTS = 2000


class InvalidTemplateContent(ValueError):
    def __init__(self, message: str, line: int | None = None):
        super().__init__(message)
        self.line = line


def _error_line(exc: Exception, rendered: bool) -> int | None:
    """Line in the submitted text; the line of a parse error refers to the rendered text when Jinja is on
    (`rendered`), which may differ from it."""
    if isinstance(exc, TemplateSyntaxError):
        return exc.lineno
    # Jinja rewrites runtime tracebacks so that template frames carry the source line.
    template_lines = [
        lineno for frame, lineno in traceback.walk_tb(exc.__traceback__) if frame.f_code.co_filename == "<template>"
    ]
    if template_lines:
        return template_lines[-1]
    if not rendered:
        if isinstance(exc, json.JSONDecodeError):
            return exc.lineno
        if isinstance(exc, yaml.MarkedYAMLError) and exc.problem_mark:
            return exc.problem_mark.line + 1
    return None


_SUBSCRIPTION_LISTS = (
    "Subscription",
    (("inbounds", "proxy objects", "inbound proxy"), ("outbounds", "proxy objects", "outbound proxy")),
)
_REQUIRED_LISTS = {
    ClientTemplateType.user_agent: ("User-Agent", (("list", "strings", "User-Agent string"),)),
    ClientTemplateType.grpc_user_agent: ("User-Agent", (("list", "strings", "User-Agent string"),)),
    ClientTemplateType.xray_subscription: _SUBSCRIPTION_LISTS,
    ClientTemplateType.singbox_subscription: _SUBSCRIPTION_LISTS,
}


def _check_rendered(template_type: ClientTemplateType, content: str, template, context: dict) -> None:
    """`template` is `content` compiled, or None when it is not Jinja."""
    if template_type == ClientTemplateType.clash_subscription:
        yaml.safe_load(
            render_compiled(
                template, {**context, "conf": {"proxies": [], "proxy-groups": [], "rules": []}, "proxy_remarks": []}
            )
        )
        return

    rendered = render_compiled(template, context) if template else content
    parsed = json.loads(rendered)
    if template_type in _REQUIRED_LISTS:
        what, items = _REQUIRED_LISTS[template_type]
        if not isinstance(parsed, dict):
            raise ValueError(f"{what} template content must render to a JSON object")
        for field, shape, one in items:
            if (value := parsed.get(field)) is None or not isinstance(value, list):
                raise ValueError(f"{what} template content must contain a '{field}' field with an array of {shape}")
            if not value:
                raise ValueError(f"{what} template content must contain at least one {one}")


def check_template_content(
    template_type: ClientTemplateType,
    content: str,
    custom_keys: Iterable[str] = (),
    host_tag_prefixes: Iterable[str] = (),
    host_count: int = 0,
    *,
    use_jinja: bool,
) -> None:
    """Render `content` the way a subscription will and check the result; raises InvalidTemplateContent.

    `hosts` holds `host_count` sample hosts: an untagged one, one per prefix in `host_tag_prefixes`, one without
    access, and the rest repeating the prefixes. A template that is fine for three hosts but too heavy for the real
    number is refused when it is saved, not when the first user fetches it.
    """
    use_jinja = effective_use_jinja(template_type, use_jinja)
    sample_hosts = sample_host_refs(host_tag_prefixes, host_count)
    custom = dict.fromkeys(custom_keys, "sample") | {"hosts": sample_hosts}
    template = None
    for sample, note in (
        (SAMPLE_FORMAT_VARIABLES, ""),
        (UNLIMITED_FORMAT_VARIABLES, " (for a user without data limit or expiry)"),
    ):
        context = {key: value for key, value in sample.items() if key not in REQUEST_VARIABLES} | custom
        try:
            if template is None and (use_jinja or template_type == ClientTemplateType.clash_subscription):
                # Once for both samples: compiling costs far more than rendering. Uncached, so drafts do not
                # evict the templates subscriptions are served from.
                template = compile_template(content, cache=False)
            _check_rendered(template_type, content, template, context)
        except Exception as exc:
            if isinstance(exc, SecurityError):
                note += f" (rendered with {len(sample_hosts)} sample hosts)"
            if use_jinja and isinstance(exc, json.JSONDecodeError | yaml.YAMLError):
                note += " (positions refer to the rendered output)"
            raise InvalidTemplateContent(f"{exc!s}{note}", _error_line(exc, use_jinja)) from exc


class ClientTemplateOperation(BaseOperation):
    @staticmethod
    async def _sync_client_template_cache() -> None:
        await refresh_client_templates_cache()
        await router.publish(MessageTopic.CLIENT_TEMPLATE, {"action": "refresh"})

    async def validate_client_template(
        self, template_type: ClientTemplateType, content: str, use_jinja: bool = False
    ) -> ClientTemplateValidation:
        custom_keys = [variable.key for variable in (await subscription_settings()).custom_variables]
        hosts = (await host_manager.get_all_hosts()).values()
        tag_prefixes = sorted({host.tag_prefix for host in hosts if host.tag_prefix})
        host_count = min(max(len(hosts) * 2, MIN_SAMPLE_HOSTS), MAX_SAMPLE_HOSTS)
        try:
            await validation_pool.run(
                check_template_content,
                template_type,
                content,
                custom_keys,
                tag_prefixes,
                host_count,
                use_jinja=use_jinja,
            )
        except TemplatesBusy as exc:
            await self.raise_error(message=str(exc), code=503)
        except InvalidTemplateContent as exc:
            return ClientTemplateValidation(valid=False, error=str(exc), line=exc.line)
        return ClientTemplateValidation(valid=True)

    async def _validate_template_content(
        self, template_type: ClientTemplateType, content: str, use_jinja: bool
    ) -> None:
        result = await self.validate_client_template(template_type, content, use_jinja)
        if not result.valid:
            await self.raise_error(message=f"Invalid template content: {result.error}", code=400)

    async def create_client_template(
        self,
        db: AsyncSession,
        new_template: ClientTemplateCreate,
        admin: AdminDetails,
    ) -> ClientTemplateResponse:
        await self._validate_template_content(new_template.template_type, new_template.content, new_template.use_jinja)

        try:
            db_template = await create_client_template(db, new_template)
        except IntegrityError:
            await self.raise_error("Template with this name already exists for this type", 409, db=db)

        logger.info(
            f'Client template "{db_template.name}" ({db_template.template_type}) created by admin "{admin.username}"'
        )
        await self._sync_client_template_cache()
        return ClientTemplateResponse.model_validate(db_template)

    async def get_client_templates(
        self,
        db: AsyncSession,
        query: ClientTemplateListQuery,
    ) -> ClientTemplateResponseList:
        templates, count = await get_client_templates(db, query=query)
        return ClientTemplateResponseList(templates=templates, count=count)

    async def get_client_templates_simple(
        self, db: AsyncSession, query: ClientTemplateSimpleListQuery
    ) -> ClientTemplatesSimpleResponse:
        rows, total = await get_client_templates_simple(db=db, query=query)

        templates = [
            ClientTemplateSimple(id=row[0], name=row[1], template_type=row[2], is_default=row[3]) for row in rows
        ]
        return ClientTemplatesSimpleResponse(templates=templates, total=total)

    async def modify_client_template(
        self,
        db: AsyncSession,
        template_id: int,
        modified_template: ClientTemplateModify,
        admin: AdminDetails,
    ) -> ClientTemplateResponse:
        db_template = await self.get_validated_client_template(db, template_id)
        template_type = ClientTemplateType(db_template.template_type)

        use_jinja = modified_template.use_jinja if modified_template.use_jinja is not None else db_template.use_jinja

        if modified_template.content is not None or modified_template.use_jinja is not None:
            content = modified_template.content if modified_template.content is not None else db_template.content
            await self._validate_template_content(template_type, content, use_jinja)

        if modified_template.is_default is False and db_template.is_default:
            await self.raise_error(
                message="Cannot unset default template directly. Set another template as default instead.",
                code=400,
            )

        try:
            db_template = await modify_client_template(db, db_template, modified_template)
        except IntegrityError:
            await self.raise_error("Template with this name already exists for this type", 409, db=db)

        logger.info(
            f'Client template "{db_template.name}" ({db_template.template_type}) modified by admin "{admin.username}"'
        )
        await self._sync_client_template_cache()
        return ClientTemplateResponse.model_validate(db_template)

    async def remove_client_template(self, db: AsyncSession, template_id: int, admin: AdminDetails) -> None:
        db_template = await self.get_validated_client_template(db, template_id)
        template_type = ClientTemplateType(db_template.template_type)

        if db_template.is_system:
            await self.raise_error(message="Cannot delete system template", code=403)

        template_count = await count_client_templates_by_type(db, template_type)
        if template_count <= 1:
            await self.raise_error(message="Cannot delete the last template for this type", code=403)

        replacement = None
        if db_template.is_default:
            replacement = await get_first_template_by_type(db, template_type, exclude_id=db_template.id)

        cleared_hosts = await clear_host_subscription_template_overrides(db, {db_template.id})
        await remove_client_template(db, db_template)

        if replacement is not None:
            await set_default_template(db, replacement)

        logger.info(
            f'Client template "{db_template.name}" ({template_type.value}) deleted by admin "{admin.username}"'
            f" and cleared from {cleared_hosts} host(s)"
        )
        await self._sync_client_template_cache()

    async def bulk_remove_client_templates(
        self, db: AsyncSession, bulk_templates: BulkClientTemplateSelection, admin: AdminDetails
    ) -> RemoveClientTemplatesResponse:
        """Remove multiple client templates by ID - fast batch delete"""
        ids_list = list(bulk_templates.ids)
        db_templates_list, _ = await get_client_templates(
            db, ClientTemplateListQuery(ids=ids_list, limit=len(ids_list))
        )

        found_ids = {t.id for t in db_templates_list}
        missing = set(ids_list) - found_ids
        if missing:
            await self.raise_error(message="Client template not found", code=404)

        db_templates = list(db_templates_list)
        templates_by_type = {}

        # Validate all templates can be deleted
        for db_template in db_templates:
            template_type = ClientTemplateType(db_template.template_type)

            if db_template.is_system:
                await self.raise_error(message=f"Cannot delete system template {db_template.name}", code=403)

            # Group templates by type for efficient counting
            if template_type not in templates_by_type:
                templates_by_type[template_type] = []
            templates_by_type[template_type].append(db_template)

        # Validate we won't leave any type without templates
        for template_type, templates_of_type in templates_by_type.items():
            total_count = await count_client_templates_by_type(db, template_type)
            if total_count <= len(templates_of_type):
                await self.raise_error(
                    message=f"Cannot delete the last template for type {template_type.value}", code=403
                )

        # Handle default template replacements
        for template_type, templates_of_type in templates_by_type.items():
            defaults_to_replace = [t for t in templates_of_type if t.is_default]
            if defaults_to_replace:
                exclude_ids = {t.id for t in templates_of_type}
                replacement = await get_first_template_by_type(db, template_type, exclude_ids=exclude_ids)
                if replacement:
                    await set_default_template(db, replacement)

        # Batch delete using CRUD function (single query)
        template_ids = [t.id for t in db_templates]
        template_names = [t.name for t in db_templates]

        cleared_hosts = await clear_host_subscription_template_overrides(db, template_ids)
        await remove_client_templates(db, template_ids)

        # Sync cache and log
        await self._sync_client_template_cache()
        for db_template in db_templates:
            template_type = ClientTemplateType(db_template.template_type)
            logger.info(
                f'Client template "{db_template.name}" ({template_type.value}) deleted by admin "{admin.username}"'
            )
        if cleared_hosts:
            logger.info(f"Cleared deleted client template overrides from {cleared_hosts} host(s)")

        return RemoveClientTemplatesResponse(templates=template_names, count=len(db_templates))
