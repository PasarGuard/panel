from app.utils.helpers import escape_ds_markdown_list
from app.models.user import UserNotificationResponse
from app.models.host import BaseHost
from app.models.user_template import UserTemplateResponse
from app.models.core import CoreResponse


def escape_md_user(user: UserNotificationResponse, by: str) -> tuple[str, str, str]:
    """Escapes markdown special characters in user and by strings for Discord."""
    return escape_ds_markdown_list((user.username, user.admin.username if user.admin else "None", by))


def escape_md_host(host: BaseHost, by: str) -> tuple[str, str, str, str]:
    """Escapes markdown special characters in host and by strings for Discord."""
    return escape_ds_markdown_list((host.remark, host.address_str, host.inbound_tag, by))


def escape_md_template(template: UserTemplateResponse, by: str) -> tuple[str, str, str, str]:
    """Escapes markdown special characters in template and by strings for Discord."""
    return escape_ds_markdown_list(
        (
            template.name,
            template.username_prefix if template.username_prefix else "",
            template.username_suffix if template.username_suffix else "",
            by,
        )
    )


def escape_md_core(core: CoreResponse, by: str) -> tuple[str, str, str, str]:
    """Escapes markdown special characters in core and by strings for Discord."""
    return escape_ds_markdown_list((core.name, core.exclude_tags, core.fallback_tags, by))
