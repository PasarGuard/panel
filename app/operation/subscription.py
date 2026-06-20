import re
from json import dumps as json_dumps
from typing import Any

from fastapi import Response
from fastapi.responses import HTMLResponse

from app.db import AsyncSession
from app.db.crud.hwid import (
    get_user_hwid_by_value,
    get_user_hwid_count,
    register_user_hwid,
)
from app.db.crud.user import get_user_usages, user_sub_update
from app.db.models import User
from app.models.admin import AdminDetails
from app.models.settings import Application, ConfigFormat, HWIDSettings, SubRule, Subscription as SubSettings
from app.models.stats import UserUsageStatsList
from app.models.subscription import SubscriptionUsageQuery
from app.models.user import SubscriptionUserResponse, UsersResponseWithInbounds
from app.settings import hwid_settings, subscription_settings
from app.subscription.share import (
    apply_custom_format_variables,
    encode_title,
    generate_subscription,
    get_effective_custom_variables,
    setup_format_variables,
)
from app.templates import render_template
from app.utils.hwid import resolve_effective_hwid_settings
from config import template_settings

from . import BaseOperation
from .user import UserOperation

client_config = {
    ConfigFormat.clash_meta: {
        "config_format": "clash_meta",
        "media_type": "text/yaml",
        "as_base64": False,
        "extension": ".yaml",
    },
    ConfigFormat.clash: {
        "config_format": "clash",
        "media_type": "text/yaml",
        "as_base64": False,
        "extension": ".yaml",
    },
    ConfigFormat.sing_box: {
        "config_format": "sing_box",
        "media_type": "application/json",
        "as_base64": False,
        "extension": ".json",
    },
    ConfigFormat.links_base64: {
        "config_format": "links",
        "media_type": "text/plain",
        "as_base64": True,
        "extension": ".txt",
    },
    ConfigFormat.links: {
        "config_format": "links",
        "media_type": "text/plain",
        "as_base64": False,
        "extension": ".txt",
    },
    ConfigFormat.outline: {
        "config_format": "outline",
        "media_type": "application/json",
        "as_base64": False,
        "extension": ".json",
    },
    ConfigFormat.wireguard: {
        "config_format": "wireguard",
        "media_type": "application/zip",
        "as_base64": False,
        "extension": ".zip",
    },
    ConfigFormat.xray: {
        "config_format": "xray",
        "media_type": "application/json",
        "as_base64": False,
        "extension": ".json",
    },
}


class SubscriptionOperation(BaseOperation):
    _ENCODED_RULE_RESPONSE_HEADERS = {"announce", "profile-title"}

    @staticmethod
    async def validated_user(db_user: User) -> UsersResponseWithInbounds:
        user = UsersResponseWithInbounds.model_validate(db_user.__dict__)
        user.inbounds = await db_user.inbounds()
        user.expire = db_user.expire
        user.lifetime_used_traffic = db_user.lifetime_used_traffic

        return user

    @staticmethod
    async def detect_client_type(user_agent: str, rules: list[SubRule]) -> ConfigFormat | None:
        """Detect the appropriate client configuration based on the user agent."""
        for rule in rules:
            if re.match(rule.pattern, user_agent):
                return rule.target

    @staticmethod
    def detect_client_rule(user_agent: str, rules: list[SubRule]) -> SubRule | None:
        """Return the first matching subscription rule for the provided user agent."""
        for rule in rules:
            if re.match(rule.pattern, user_agent):
                return rule
        return None

    @staticmethod
    def _format_profile_title(
        user: UsersResponseWithInbounds, format_variables: dict, sub_settings: SubSettings
    ) -> str:
        """Format profile title with dynamic variables, falling back to default if needed."""
        # Prefer admin's profile_title over subscription settings
        profile_title = (
            getattr(user.admin, "profile_title", None) if user.admin else None
        ) or sub_settings.profile_title

        if not profile_title:
            return "Subscription"

        try:
            return profile_title.format_map(format_variables)
        except ValueError, KeyError:
            # Invalid format string, return original title
            return profile_title

    @staticmethod
    def _format_announce(sub_settings: SubSettings, format_variables: dict) -> str:
        """Format announcement text with dynamic variables, falling back to raw text if needed."""
        if not sub_settings.announce:
            return ""

        try:
            return sub_settings.announce.format_map(format_variables)
        except ValueError, KeyError:
            return sub_settings.announce

    @staticmethod
    def create_response_headers(
        user: UsersResponseWithInbounds,
        request_url: str,
        sub_settings: SubSettings,
        inline: bool = False,
        extra_headers: dict[str, str] | None = None,
        extension: str = "",
    ) -> dict:
        """Create response headers for subscription responses, including user subscription info."""
        # Generate user subscription info
        user_info = {"upload": 0, "download": user.used_traffic, "total": 0, "expire": 0}

        if user.data_limit:
            user_info["total"] = user.data_limit

        if user.expire:
            user_info["expire"] = int(user.expire.timestamp())

        # Format profile title with dynamic variables
        custom_variables = get_effective_custom_variables(user, sub_settings.custom_variables)
        format_variables = setup_format_variables(user, sub_settings.custom_variables)
        format_variables.update({"url": request_url})
        formatted_title = SubscriptionOperation._format_profile_title(user, format_variables, sub_settings)
        format_variables.update({"PROFILE_TITLE": formatted_title})
        apply_custom_format_variables(format_variables, custom_variables)
        formatted_announce = SubscriptionOperation._format_announce(sub_settings, format_variables)

        # Prefer admin's support_url over subscription settings
        support_url = (getattr(user.admin, "support_url", None) if user.admin else None) or sub_settings.support_url

        # Use 'inline' for browser viewing, 'attachment' for download
        disposition = "inline" if inline else "attachment"

        headers = {
            "content-disposition": f'{disposition}; filename="{user.username}{extension}"',
            "profile-web-page-url": request_url,
            "support-url": support_url,
            "profile-title": encode_title(formatted_title),
            "profile-update-interval": str(sub_settings.update_interval),
            "subscription-userinfo": "; ".join(f"{key}={val}" for key, val in user_info.items()),
            "announce": encode_title(formatted_announce),
            "announce-url": sub_settings.announce_url,
        }
        if extra_headers:
            headers.update(extra_headers)
        return headers

    @classmethod
    def _format_rule_response_headers(
        cls, rule: SubRule | None, format_variables: dict[str, str | int | float]
    ) -> dict[str, str]:
        if not rule or not rule.response_headers:
            return {}

        headers: dict[str, str] = {}
        for raw_name, raw_value in rule.response_headers.items():
            header_name = str(raw_name).strip()
            if not header_name or raw_value is None:
                continue

            formatted_value = cls._stringify_rule_header_value(raw_value, format_variables)
            if not formatted_value:
                continue

            if header_name.lower() in cls._ENCODED_RULE_RESPONSE_HEADERS:
                formatted_value = encode_title(formatted_value)

            headers[header_name] = formatted_value

        return headers

    @classmethod
    def _format_subscription_response_headers(
        cls, sub_settings: SubSettings, format_variables: dict[str, str | int | float]
    ) -> dict[str, str]:
        if not sub_settings.response_headers:
            return {}

        headers: dict[str, str] = {}
        for raw_name, raw_value in sub_settings.response_headers.items():
            header_name = str(raw_name).strip()
            if not header_name or raw_value is None:
                continue

            formatted_value = cls._stringify_rule_header_value(raw_value, format_variables)
            if not formatted_value:
                continue

            if header_name.lower() in cls._ENCODED_RULE_RESPONSE_HEADERS:
                formatted_value = encode_title(formatted_value)

            headers[header_name] = formatted_value

        return headers

    @staticmethod
    def _stringify_rule_header_value(value: Any, format_variables: dict[str, str | int | float]) -> str:
        if isinstance(value, str):
            header_value = value.strip()
            if not header_value:
                return ""
            try:
                return header_value.format_map(format_variables)
            except ValueError, KeyError:
                return header_value

        if isinstance(value, (dict, list, tuple, bool, int, float)):
            return json_dumps(value, ensure_ascii=False, separators=(",", ":"))

        return str(value).strip()

    @staticmethod
    def create_info_response_headers(user: UsersResponseWithInbounds, sub_settings: SubSettings) -> dict:
        """Create response headers for /info endpoint with only support-url, announce, and announce-url."""
        # Prefer admin's support_url over subscription settings
        support_url = (getattr(user.admin, "support_url", None) if user.admin else None) or sub_settings.support_url
        formatted_announce = SubscriptionOperation._format_announce(
            sub_settings,
            setup_format_variables(user, sub_settings.custom_variables),
        )

        headers = {
            "support-url": support_url,
            "announce": encode_title(formatted_announce),
            "announce-url": sub_settings.announce_url,
        }

        # Only include headers that have values
        return {k: v for k, v in headers.items() if v}

    async def fetch_config(self, user: UsersResponseWithInbounds, client_type: ConfigFormat) -> tuple[str | bytes, str]:
        # Get client configuration
        config = client_config.get(client_type, {})
        sub_settings = await subscription_settings()
        randomize_order = sub_settings.randomize_order

        # Generate subscription content
        return (
            await generate_subscription(
                user=user,
                config_format=config.get("config_format", ""),
                as_base64=config.get("as_base64", ""),
                randomize_order=randomize_order,
            ),
            config["media_type"],
        )

    @staticmethod
    def is_hwid_enabled(
        global_hwid_conf: HWIDSettings,
        effective_hwid_conf: HWIDSettings | None,
        user_hwid_limit: int | None,
        *,
        is_manual_sub: bool = False,
    ) -> bool:
        if effective_hwid_conf is None or not effective_hwid_conf.enabled:
            return False

        # An explicit hwid_limit of 0 opts the user out of HWID entirely, even under a
        # forced global/role policy. None is distinct: it falls back to forced/fallback.
        if user_hwid_limit == 0:
            return False

        effective_limit = SubscriptionOperation.resolve_subscription_hwid_limit(
            user_hwid_limit,
            effective_hwid_conf,
        )
        forced = effective_hwid_conf.forced
        if is_manual_sub and not global_hwid_conf.require_hwid_for_manual_sub:
            forced = False

        return forced or (effective_limit is not None and effective_limit > 0)

    @staticmethod
    def resolve_subscription_hwid_limit(
        user_hwid_limit: int | None,
        effective_hwid_conf: HWIDSettings | None,
    ) -> int | None:
        if user_hwid_limit is not None:
            return user_hwid_limit
        if effective_hwid_conf is None or not effective_hwid_conf.enabled:
            return None
        return effective_hwid_conf.fallback_limit

    async def is_user_hwid_enabled(self, db_user: User, *, is_manual_sub: bool = False) -> bool:
        role_hwid_settings = db_user.admin.role.hwid if db_user.admin and db_user.admin.role else None
        global_hwid_conf: HWIDSettings = await hwid_settings()
        effective_hwid_conf = resolve_effective_hwid_settings(global_hwid_conf, role_hwid_settings)
        return self.is_hwid_enabled(
            global_hwid_conf,
            effective_hwid_conf,
            db_user.hwid_limit,
            is_manual_sub=is_manual_sub,
        )

    async def validate_and_register_hwid(
        self,
        db: AsyncSession,
        user_id: int,
        user_hwid_limit: int | None,
        role_hwid_settings: HWIDSettings | dict | None,
        x_hwid: str | None,
        x_device_os: str | None,
        x_ver_os: str | None,
        x_device_model: str | None,
        is_manual_sub: bool = False,
    ):
        global_hwid_conf: HWIDSettings = await hwid_settings()
        effective_hwid_conf = resolve_effective_hwid_settings(global_hwid_conf, role_hwid_settings)

        # Registration is gated on the master "enabled" switch only: whenever HWID is
        # enabled we record/refresh the device on any request that carries an X-HWID,
        # independent of forced/limit. `forced` only controls whether the header is
        # required; `limit` only caps the number of distinct devices. An explicit
        # hwid_limit of 0 opts the user out entirely.
        if effective_hwid_conf is None or not effective_hwid_conf.enabled or user_hwid_limit == 0:
            return

        forced = effective_hwid_conf.forced
        if is_manual_sub and not global_hwid_conf.require_hwid_for_manual_sub:
            forced = False

        limit = self.resolve_subscription_hwid_limit(user_hwid_limit, effective_hwid_conf)

        if not x_hwid:
            # Only a forced policy requires the header. A bare limit just caps device
            # count (enforced below once an X-HWID is actually presented).
            if forced:
                await self.raise_error(message="HWID header required", code=403)
            return

        existing_hwid = await get_user_hwid_by_value(db, user_id, x_hwid)
        if existing_hwid:
            await register_user_hwid(db, user_id, x_hwid, x_device_os, x_ver_os, x_device_model)
            return

        # It's a new HWID, check limit
        if limit is not None and limit > 0:
            current_count = await get_user_hwid_count(db, user_id)
            if current_count >= limit:
                await self.raise_error(message="Device limit reached", code=403)

        await register_user_hwid(db, user_id, x_hwid, x_device_os, x_ver_os, x_device_model)

    async def user_subscription(
        self,
        db: AsyncSession,
        token: str,
        accept_header: str = "",
        user_agent: str = "",
        ip: str | None = None,
        request_url: str = "",
        x_hwid: str | None = None,
        x_device_os: str | None = None,
        x_ver_os: str | None = None,
        x_device_model: str | None = None,
    ):
        """
        Provides a subscription link based on the user agent (Clash, V2Ray, etc.).
        """
        sub_settings: SubSettings = await subscription_settings()
        db_user = await self.get_validated_sub(db, token, load_admin_role=True)
        role_hwid_settings = db_user.admin.role.hwid if db_user.admin and db_user.admin.role else None
        user = await self.validated_user(db_user)
        is_browser_request = "text/html" in accept_header
        is_subscription_page_request = is_browser_request and not sub_settings.disable_sub_template
        if is_subscription_page_request:
            is_hwid_enabled = await self.is_user_hwid_enabled(db_user)
            template = (
                db_user.admin.sub_template
                if db_user.admin and db_user.admin.sub_template
                else template_settings.subscription_page_template
            )
            is_allow_browser_config = sub_settings.allow_browser_config and not is_hwid_enabled
            links = []
            if is_allow_browser_config:
                conf, media_type = await self.fetch_config(
                    user,
                    ConfigFormat.links,
                )
                links = conf.splitlines()

            format_variables = await self.get_format_variables(user)
            formatted_announce = self._format_announce(sub_settings, format_variables)

            return HTMLResponse(
                render_template(
                    template,
                    self._build_subscription_body_payload(
                        user, links, formatted_announce, sub_settings, format_variables, is_hwid_enabled
                    ),
                )
            )
        else:
            await self.validate_and_register_hwid(
                db,
                db_user.id,
                db_user.hwid_limit,
                role_hwid_settings,
                x_hwid,
                x_device_os,
                x_ver_os,
                x_device_model,
            )
            matched_rule = self.detect_client_rule(user_agent, sub_settings.rules)
            client_type = matched_rule.target if matched_rule else None
            if client_type == ConfigFormat.block or not client_type:
                await self.raise_error(message="Client not supported", code=406)

            # Update user subscription info
            await user_sub_update(db, db_user.id, user_agent, ip=ip, hwid=x_hwid)
            conf, media_type = await self.fetch_config(user, client_type)

            # If disable_sub_template is True and it's a browser request, use inline to view instead of download
            inline_view = sub_settings.disable_sub_template and is_browser_request
            response_headers = self.create_response_headers(
                user,
                request_url,
                sub_settings,
                inline=inline_view,
                extra_headers={},
            )
            try:
                response_headers.update(
                    self._format_subscription_response_headers(
                        sub_settings, await self._get_rule_response_header_variables(user, client_type)
                    )
                )
                response_headers.update(
                    self._format_rule_response_headers(
                        matched_rule, await self._get_rule_response_header_variables(user, client_type)
                    )
                )
                response_headers = self.sanitize_response_headers(response_headers)
            except ValueError as exc:
                await self.raise_error(message=str(exc), code=400)

        # Create response with appropriate headers
        return Response(content=conf, media_type=media_type, headers=response_headers)

    async def get_format_variables(self, user: UsersResponseWithInbounds) -> dict:
        """Get format variables for URL formatting."""
        sub_settings: SubSettings = await subscription_settings()
        custom_variables = get_effective_custom_variables(user, sub_settings.custom_variables)
        format_variables = setup_format_variables(user, sub_settings.custom_variables)
        sub_url = await UserOperation.generate_subscription_url(user)
        format_variables.update({"url": sub_url})
        formatted_title = SubscriptionOperation._format_profile_title(user, format_variables, sub_settings)

        format_variables.update({"PROFILE_TITLE": formatted_title})
        apply_custom_format_variables(format_variables, custom_variables)

        return format_variables

    async def _get_rule_response_header_variables(
        self, user: UsersResponseWithInbounds, client_format: ConfigFormat
    ) -> dict[str, str | int | float]:
        format_variables = await self.get_format_variables(user)
        format_variables.update({"format": client_format.value})
        sub_settings: SubSettings = await subscription_settings()
        apply_custom_format_variables(
            format_variables, get_effective_custom_variables(user, sub_settings.custom_variables)
        )
        return format_variables

    async def user_subscription_with_client_type(
        self,
        db: AsyncSession,
        token: str,
        client_type: ConfigFormat,
        request_url: str = "",
        x_hwid: str | None = None,
        x_device_os: str | None = None,
        x_ver_os: str | None = None,
        x_device_model: str | None = None,
    ):
        """Provides a subscription link based on the specified client type (e.g., Clash, V2Ray)."""
        sub_settings: SubSettings = await subscription_settings()

        if client_type == ConfigFormat.block or not getattr(sub_settings.manual_sub_request, client_type):
            await self.raise_error(message="Client not supported", code=406)
        db_user = await self.get_validated_sub(db, token=token, load_admin_role=True)
        user = await self.validated_user(db_user)

        await self.validate_and_register_hwid(
            db,
            db_user.id,
            db_user.hwid_limit,
            db_user.admin.role.hwid if db_user.admin and db_user.admin.role else None,
            x_hwid,
            x_device_os,
            x_ver_os,
            x_device_model,
            is_manual_sub=True,
        )

        response_headers = self.create_response_headers(
            user, request_url, sub_settings, extension=client_config.get(client_type, {}).get("extension", "")
        )
        try:
            response_headers.update(
                self._format_subscription_response_headers(
                    sub_settings, await self._get_rule_response_header_variables(user, client_type)
                )
            )
            response_headers = self.sanitize_response_headers(response_headers)
        except ValueError as exc:
            await self.raise_error(message=str(exc), code=400)
        conf, media_type = await self.fetch_config(user, client_type)

        # Create response headers
        return Response(content=conf, media_type=media_type, headers=response_headers)

    def _build_subscription_body_payload(
        self,
        user: UsersResponseWithInbounds,
        links: list[str],
        formatted_announce: str,
        sub_settings: SubSettings,
        format_variables: dict,
        is_hwid_enabled: bool,
    ) -> dict[str, Any]:
        return {
            "user": SubscriptionUserResponse.model_validate(user),
            "links": links,
            "announce": formatted_announce,
            "announce_url": sub_settings.announce_url,
            "apps": self._make_apps_import_urls(
                sub_settings.applications,
                format_variables,
                is_hwid_enabled=is_hwid_enabled,
            ),
        }

    def _build_raw_subscription_payload(
        self,
        user: UsersResponseWithInbounds,
        links: list[str],
        formatted_announce: str,
        sub_settings: SubSettings,
        format_variables: dict,
        headers: dict[str, str],
        is_hwid_enabled: bool,
    ) -> dict[str, Any]:
        return {
            "body": self._build_subscription_body_payload(
                user, links, formatted_announce, sub_settings, format_variables, is_hwid_enabled
            ),
            "headers": headers,
        }

    async def user_subscription_raw(self, db: AsyncSession, token: str, request_url: str = ""):
        sub_settings: SubSettings = await subscription_settings()
        db_user = await self.get_validated_sub(db, token, load_admin_role=True)
        user = await self.validated_user(db_user)
        is_hwid_enabled = await self.is_user_hwid_enabled(db_user)

        links = []
        if sub_settings.allow_browser_config:
            conf, _ = await self.fetch_config(user, ConfigFormat.links)
            links = conf.splitlines()
        format_variables = await self.get_format_variables(user)
        formatted_announce = self._format_announce(sub_settings, format_variables)
        response_headers = self.create_response_headers(user, request_url, sub_settings)
        try:
            response_headers.update(
                self._format_subscription_response_headers(
                    sub_settings, await self._get_rule_response_header_variables(user, ConfigFormat.links)
                )
            )
            response_headers = self.sanitize_response_headers(response_headers)
        except ValueError as exc:
            await self.raise_error(message=str(exc), code=400)

        return self._build_raw_subscription_payload(
            user,
            links,
            formatted_announce,
            sub_settings,
            format_variables,
            response_headers,
            is_hwid_enabled,
        )

    async def user_subscription_by_user(
        self,
        db_user: User,
        client_type: ConfigFormat,
        request_url: str = "",
    ):
        if client_type == ConfigFormat.block:
            await self.raise_error(message="Client not supported", code=406)

        sub_settings: SubSettings = await subscription_settings()
        user = await self.validated_user(db_user)

        response_headers = self.create_response_headers(
            user, request_url, sub_settings, extension=client_config.get(client_type, {}).get("extension", "")
        )
        try:
            response_headers.update(
                self._format_subscription_response_headers(
                    sub_settings, await self._get_rule_response_header_variables(user, client_type)
                )
            )
            response_headers = self.sanitize_response_headers(response_headers)
        except ValueError as exc:
            await self.raise_error(message=str(exc), code=400)
        conf, media_type = await self.fetch_config(user, client_type)

        return Response(content=conf, media_type=media_type, headers=response_headers)

    async def user_subscription_by_id(
        self, db: AsyncSession, user_id: int, admin: AdminDetails, client_type: ConfigFormat, request_url: str = ""
    ):
        db_user = await self.get_validated_user_by_id(db, user_id, admin)
        return await self.user_subscription_by_user(db_user, client_type, request_url)

    async def user_subscription_info(
        self, db: AsyncSession, token: str, ip: str | None = None
    ) -> tuple[SubscriptionUserResponse, dict]:
        """Retrieves detailed information about the user's subscription."""
        sub_settings: SubSettings = await subscription_settings()
        db_user = await self.get_validated_sub(db, token=token)
        user = await self.validated_user(db_user)

        response_headers = self.create_info_response_headers(user, sub_settings)
        try:
            response_headers = self.sanitize_response_headers(response_headers)
        except ValueError as exc:
            await self.raise_error(message=str(exc), code=400)
        user_response = SubscriptionUserResponse.model_validate(db_user)
        user_response.ip = ip

        return user_response, response_headers

    async def user_subscription_apps(self, db: AsyncSession, token: str) -> list[Application]:
        """
        Get available applications for user's subscription.
        """
        db_user = await self.get_validated_sub(db, token=token, load_admin_role=True)
        user = await self.validated_user(db_user)
        is_hwid_enabled = await self.is_user_hwid_enabled(db_user)
        sub_settings: SubSettings = await subscription_settings()
        format_variables = await self.get_format_variables(user)
        return self._make_apps_import_urls(
            sub_settings.applications,
            format_variables,
            is_hwid_enabled=is_hwid_enabled,
        )

    def _make_apps_import_urls(
        self, applications: list[Application], format_variables: dict, *, is_hwid_enabled: bool
    ) -> list[Application]:
        apps_with_updated_urls = []
        for app in applications:
            updated_app = app.model_copy()
            import_url = app.import_url.format_map(format_variables)
            updated_app.import_url = import_url
            if is_hwid_enabled:
                if app.show_when_hwid_enabled:
                    apps_with_updated_urls.append(updated_app)
            else:
                apps_with_updated_urls.append(updated_app)

        return apps_with_updated_urls

    async def get_user_usage(
        self,
        db: AsyncSession,
        token: str,
        query: SubscriptionUsageQuery,
    ) -> UserUsageStatsList:
        """Fetches the usage statistics for the user within a specified date range."""
        start, end = await self.validate_dates(query.start, query.end, True)

        db_user = await self.get_validated_sub(db, token=token)

        return await get_user_usages(db, db_user.id, start, end, query.period)
