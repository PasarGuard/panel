from aiocache import cached

from app.db import GetDB
from app.db.crud.client_profile import get_all_client_profiles
from app.db.crud.client_template import TEMPLATE_TYPE_TO_LEGACY_KEY
from app.models.client_profile import ClientProfile, ClientProfileTemplateType
from app.models.client_template import ClientTemplateType
from app.models.settings import Subscription as SubSettings
from app.subscription.client_templates import subscription_client_templates, subscription_template_contents
from app.subscription.config_cache import clear_sub_config_cache

# Settings a profile overrides directly over the global subscription settings (first non-empty wins).
_GLOBAL_OVERRIDE_FIELDS = ("announce", "announce_url", "update_interval", "randomize_order")


@cached()
async def subscription_client_profiles() -> dict[int, ClientProfile]:
    async with GetDB() as db:
        return {profile.id: ClientProfile.model_validate(profile) for profile in await get_all_client_profiles(db)}


async def get_client_profile(profile_id: int | None) -> ClientProfile | None:
    if profile_id is None:
        return None
    return (await subscription_client_profiles()).get(profile_id)


async def refresh_client_profiles_cache() -> None:
    await subscription_client_profiles.cache.clear()
    clear_sub_config_cache()


async def handle_client_profile_message(_: dict) -> None:
    """Handle client profile update messages from NATS router."""
    await refresh_client_profiles_cache()


def resolve_client_template(
    template_type: ClientProfileTemplateType,
    profile: ClientProfile | None,
    defaults: dict[str, str],
    contents_by_id: dict[int, str],
) -> str | None:
    """Template content for one whole-config type: profile template > global default.

    Host-level xray templates are applied per host on top of this (XrayConfiguration.add).
    Extend here for higher-priority sources (e.g. a per-rule template).
    """
    if profile is not None:
        template_id = profile.templates.get(template_type)
        if template_id is not None and (content := contents_by_id.get(template_id)):
            return content
    return defaults.get(TEMPLATE_TYPE_TO_LEGACY_KEY[ClientTemplateType(template_type.value)])


async def resolve_client_templates(profile: ClientProfile | None) -> dict[str, str]:
    """Legacy-keyed client templates (as subscription_client_templates) with the profile's choices applied."""
    defaults = await subscription_client_templates()
    if profile is None or not profile.templates:
        return defaults

    contents_by_id = await subscription_template_contents()
    resolved = dict(defaults)
    for template_type in profile.templates:
        content = resolve_client_template(template_type, profile, defaults, contents_by_id)
        if content is not None:
            resolved[TEMPLATE_TYPE_TO_LEGACY_KEY[ClientTemplateType(template_type.value)]] = content
    return resolved


def apply_client_profile_settings(sub_settings: SubSettings, profile: ClientProfile | None) -> SubSettings:
    """Global subscription settings with the profile's overrides.

    profile_title, support_url (profile > admin > global), custom variables (global, admin, profile)
    and remove_response_headers are applied where they are used, since they also involve the admin
    or the final header set.
    """
    if profile is None:
        return sub_settings

    overrides = profile.settings
    update = {}
    for field in _GLOBAL_OVERRIDE_FIELDS:
        value = getattr(overrides, field)
        if value is not None:
            update[field] = value

    if overrides.response_headers:
        overridden = {name.lower() for name in overrides.response_headers}
        response_headers = {
            name: value for name, value in sub_settings.response_headers.items() if str(name).lower() not in overridden
        }
        response_headers.update(overrides.response_headers)
        update["response_headers"] = response_headers

    return sub_settings.model_copy(update=update) if update else sub_settings


def drop_removed_response_headers(headers: dict[str, str], profile: ClientProfile | None) -> dict[str, str]:
    """Remove the profile's remove_response_headers from a header dict (case-insensitive)."""
    if profile is None or not profile.settings.remove_response_headers:
        return headers
    removed = {name.lower() for name in profile.settings.remove_response_headers}
    return {name: value for name, value in headers.items() if name.lower() not in removed}
