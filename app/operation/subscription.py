import re
from datetime import datetime as dt

from fastapi import Response
from fastapi.responses import HTMLResponse

from app.db import AsyncSession
from app.db.crud.user import get_user_usages, user_sub_update
from app.db.models import User
from app.models.settings import Application, ConfigFormat, SubRule, Subscription as SubSettings
from app.models.stats import Period, UserUsageStatsList
from app.models.user import SubscriptionUserResponse, UsersResponseWithInbounds
from app.settings import subscription_settings
from app.subscription.share import encode_title, generate_subscription, setup_format_variables
from app.templates import render_template
from config import SUBSCRIPTION_PAGE_TEMPLATE

from . import BaseOperation

client_config = {
    ConfigFormat.clash_meta: {"config_format": "clash_meta", "media_type": "text/yaml", "as_base64": False},
    ConfigFormat.clash: {"config_format": "clash", "media_type": "text/yaml", "as_base64": False},
    ConfigFormat.sing_box: {"config_format": "sing_box", "media_type": "application/json", "as_base64": False},
    ConfigFormat.links_base64: {"config_format": "links", "media_type": "text/plain", "as_base64": True},
    ConfigFormat.links: {"config_format": "links", "media_type": "text/plain", "as_base64": False},
    ConfigFormat.outline: {"config_format": "outline", "media_type": "application/json", "as_base64": False},
    ConfigFormat.xray: {"config_format": "xray", "media_type": "application/json", "as_base64": False},
}


class SubscriptionOperation(BaseOperation):
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
        except (ValueError, KeyError):
            # Invalid format string, return original title
            return profile_title

    @staticmethod
    def create_response_headers(user: UsersResponseWithInbounds, request_url: str, sub_settings: SubSettings) -> dict:
        """Create response headers for subscription responses, including user subscription info."""
        # Generate user subscription info
        user_info = {"upload": 0, "download": user.used_traffic, "total": 0, "expire": 0}

        if user.data_limit:
            user_info["total"] = user.data_limit

        if user.expire:
            user_info["expire"] = int(user.expire.timestamp())

        # Format profile title with dynamic variables
        format_variables = setup_format_variables(user)
        formatted_title = SubscriptionOperation._format_profile_title(user, format_variables, sub_settings)

        # Prefer admin's support_url over subscription settings
        support_url = (getattr(user.admin, "support_url", None) if user.admin else None) or sub_settings.support_url

        return {
            "content-disposition": f'attachment; filename="{user.username}"',
            "profile-web-page-url": request_url,
            "support-url": support_url,
            "profile-title": encode_title(formatted_title),
            "profile-update-interval": str(sub_settings.update_interval),
            "subscription-userinfo": "; ".join(f"{key}={val}" for key, val in user_info.items()),
            "announce": encode_title(sub_settings.announce),
            "announce-url": sub_settings.announce_url,
        }

    @staticmethod
    def create_info_response_headers(user: UsersResponseWithInbounds, sub_settings: SubSettings) -> dict:
        """Create response headers for /info endpoint with only support-url, announce, and announce-url."""
        # Prefer admin's support_url over subscription settings
        support_url = (getattr(user.admin, "support_url", None) if user.admin else None) or sub_settings.support_url

        headers = {
            "support-url": support_url,
            "announce": encode_title(sub_settings.announce),
            "announce-url": sub_settings.announce_url,
        }

        # Only include headers that have values
        return {k: v for k, v in headers.items() if v}

    async def fetch_config(self, user: UsersResponseWithInbounds, client_type: ConfigFormat) -> tuple[str, str]:
        # Get client configuration
        config = client_config.get(client_type)

        # Generate subscription content
        return (
            await generate_subscription(
                user=user,
                config_format=config["config_format"],
                as_base64=config["as_base64"],
            ),
            config["media_type"],
        )

    async def user_subscription(
        self,
        db: AsyncSession,
        token: str,
        accept_header: str = "",
        user_agent: str = "",
        request_url: str = "",
    ):
        """Provides a subscription link based on the user agent (Clash, V2Ray, etc.)."""
        # Handle HTML request (subscription page)
        sub_settings: SubSettings = await subscription_settings()
        db_user = await self.get_validated_sub(db, token)
        user = await self.validated_user(db_user)

        response_headers = self.create_response_headers(user, request_url, sub_settings)

        if "text/html" in accept_header:
            template = (
                db_user.admin.sub_template
                if db_user.admin and db_user.admin.sub_template
                else SUBSCRIPTION_PAGE_TEMPLATE
            )
            conf, media_type = await self.fetch_config(user, ConfigFormat.links)

            return HTMLResponse(
                render_template(
                    template,
                    {
                        "user": user,
                        "links": conf.split("\n"),
                        "apps": self._make_apps_import_urls(request_url, sub_settings.applications),
                    },
                )
            )
        else:
            client_type = await self.detect_client_type(user_agent, sub_settings.rules)
            if client_type == ConfigFormat.block or not client_type:
                await self.raise_error(message="Client not supported", code=406)

            # Update user subscription info
            await user_sub_update(db, db_user.id, user_agent)
            conf, media_type = await self.fetch_config(user, client_type)

        # Create response with appropriate headers
        return Response(content=conf, media_type=media_type, headers=response_headers)

    async def user_subscription_with_client_type(
        self, db: AsyncSession, token: str, client_type: ConfigFormat, request_url: str = ""
    ):
        """Provides a subscription link based on the specified client type (e.g., Clash, V2Ray)."""
        sub_settings: SubSettings = await subscription_settings()

        if client_type == ConfigFormat.block or not getattr(sub_settings.manual_sub_request, client_type):
            await self.raise_error(message="Client not supported", code=406)
        db_user = await self.get_validated_sub(db, token=token)
        user = await self.validated_user(db_user)

        response_headers = self.create_response_headers(user, request_url, sub_settings)
        conf, media_type = await self.fetch_config(user, client_type)

        # Create response headers
        return Response(content=conf, media_type=media_type, headers=response_headers)

    async def user_subscription_info(
        self, db: AsyncSession, token: str, request_url: str = ""
    ) -> tuple[SubscriptionUserResponse, dict]:
        """Retrieves detailed information about the user's subscription."""
        sub_settings: SubSettings = await subscription_settings()
        db_user = await self.get_validated_sub(db, token=token)
        user = await self.validated_user(db_user)

        response_headers = self.create_info_response_headers(user, sub_settings)
        user_response = SubscriptionUserResponse.model_validate(db_user.__dict__)

        return user_response, response_headers

    async def user_subscription_apps(self, db: AsyncSession, token: str, request_url: str) -> list[Application]:
        """
        Get available applications for user's subscription.
        """
        _, _ = await self.user_subscription_info(db, token, request_url)
        sub_settings: SubSettings = await subscription_settings()
        return self._make_apps_import_urls(request_url, sub_settings.applications)

    def _make_apps_import_urls(self, request_url: str, applications: list[Application]):
        apps_with_updated_urls = []
        for app in applications:
            updated_app = app.model_copy()
            updated_app.import_url = app.import_url.format(url=request_url)
            apps_with_updated_urls.append(updated_app)

        return apps_with_updated_urls

    async def get_user_usage(
        self,
        db: AsyncSession,
        token: str,
        start: dt = None,
        end: dt = None,
        period: Period = Period.hour,
    ) -> UserUsageStatsList:
        """Fetches the usage statistics for the user within a specified date range."""
        start, end = await self.validate_dates(start, end, True)

        db_user = await self.get_validated_sub(db, token=token)

        return await get_user_usages(db, db_user.id, start, end, period)
