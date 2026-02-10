import html
import json
import re
from datetime import datetime as dt, timezone as tz
from typing import Union
from uuid import UUID

from pydantic import ValidationError


def yml_uuid_representer(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", str(data))


def readable_datetime(date_time: Union[dt, int, None], include_date: bool = True, include_time: bool = True):
    def get_datetime_format():
        dt_format = ""
        if include_date:
            dt_format += "%d %B %Y"
        if include_time:
            if dt_format:
                dt_format += ", "
            dt_format += "%H:%M:%S"

        return dt_format

    if isinstance(date_time, int):
        date_time = dt.fromtimestamp(date_time)

    return date_time.strftime(get_datetime_format()) if date_time else "-"


def fix_datetime_timezone(value: dt | int | str):
    if isinstance(value, dt):
        # If datetime is naive (no timezone), assume it's UTC
        if value.tzinfo is None:
            return value.replace(tzinfo=tz.utc)
        return value  # Already has timezone info
    elif isinstance(value, int):
        # Timestamp will be assume it's UTC
        return dt.fromtimestamp(value, tz=tz.utc)
    elif isinstance(value, str):
        # SQLite strftime returns naive ISO strings; treat them as UTC.
        parsed = dt.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=tz.utc)
        return parsed

    raise ValueError("input can be datetime or timestamp")


def ensure_datetime_timezone(value: dt | int | str, default_tz: tz = tz.utc) -> dt:
    """
    Ensures datetime has timezone info WITHOUT converting to UTC.

    Args:
        value: Input datetime, timestamp, or ISO string
        default_tz: Timezone to use if input is naive (default: UTC)

    Returns:
        Timezone-aware datetime preserving original timezone
    """
    if isinstance(value, dt):
        # If datetime is naive, add default timezone
        if value.tzinfo is None:
            return value.replace(tzinfo=default_tz)
        # If datetime has timezone, KEEP IT (don't convert to UTC)
        return value
    elif isinstance(value, int):
        # Timestamp assumed to be UTC
        return dt.fromtimestamp(value, tz=default_tz)
    elif isinstance(value, str):
        # Parse ISO string
        parsed = dt.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=default_tz)
        return parsed

    raise ValueError("input can be datetime, timestamp, or ISO string")


def get_timezone_offset_string(dt_value: dt) -> str | None:
    """
    Extract timezone offset string from a datetime object.

    Args:
        dt_value: Datetime object with timezone info

    Returns:
        Timezone offset string in format '+HH:MM' or '-HH:MM', or None if no timezone

    Examples:
        >>> from datetime import datetime, timezone, timedelta
        >>> dt_tehran = datetime(2024, 1, 1, tzinfo=timezone(timedelta(hours=3, minutes=30)))
        >>> get_timezone_offset_string(dt_tehran)
        '+03:30'
    """
    if dt_value is None or dt_value.tzinfo is None:
        return None

    offset = dt_value.utcoffset()
    if offset is None:
        return None

    total_seconds = int(offset.total_seconds())
    hours, remainder = divmod(abs(total_seconds), 3600)
    minutes = remainder // 60
    sign = "+" if total_seconds >= 0 else "-"
    return f"{sign}{hours:02d}:{minutes:02d}"


class UUIDEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, UUID):
            # if the obj is uuid, we simply return the value of uuid
            return str(obj)
        return super().default(self, obj)


def format_validation_error(error: ValidationError) -> str:
    return "\n".join([e["loc"][0].replace("_", " ").capitalize() + ": " + e["msg"] for e in error.errors()])


def escape_tg_html(list: tuple[str]) -> tuple[str]:
    """Escapes HTML special characters for the telegram HTML parser."""
    return tuple(html.escape(text) for text in list)


def escape_ds_markdown(text: str) -> str:
    """Escapes markdown special characters for Discord."""
    # Other characters like >, |, [, ], (, ) are often handled by Discord's parser
    # or are part of specific markdown constructs (e.g., links, blockquotes)
    # that might not need general escaping.
    escape_chars = r"[*_`~]"
    return re.sub(escape_chars, r"\\\g<0>", text)


def escape_ds_markdown_list(list: tuple[str]) -> tuple[str]:
    """Escapes markdown special characters for Discord."""
    return tuple(escape_ds_markdown(text) for text in list)
