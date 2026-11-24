from app.models.core import CoreResponse
from app.models.host import BaseHost
from app.models.user import UserNotificationResponse
from app.models.user_template import UserTemplateResponse
from app.notification.user_details import MODIFY_CURRENT, MODIFY_DIFF, change_rows, user_rows
from app.utils.helpers import escape_ds_markdown_list


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


def user_details_md(user: UserNotificationResponse, fields: tuple[str, ...], **extra) -> str:
    """Renders the user detail rows, each on its own line, ready to follow the username line."""
    return "".join(
        f"\n**{label}:** {value}"
        for label, value in (escape_ds_markdown_list(row) for row in user_rows(user, fields, **extra))
    )


def user_changes_md(user: UserNotificationResponse, previous: UserNotificationResponse) -> str:
    """Renders what a modify changed, then the current fields that did not change."""
    changes = change_rows(previous, user, MODIFY_DIFF)
    changed = {name for name, *_ in changes}
    lines = "".join(
        f"\n**{label}:** {old} → {new}"
        for label, old, new in (escape_ds_markdown_list(change[1:]) for change in changes)
    )
    return lines + user_details_md(user, tuple(name for name in MODIFY_CURRENT if name not in changed))
