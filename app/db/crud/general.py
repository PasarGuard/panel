from sqlalchemy import String, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import JWT, System
from app.models.stats import Period

MYSQL_FORMATS = {
    Period.minute: "%Y-%m-%d %H:%i:00",
    Period.hour: "%Y-%m-%d %H:00:00",
    Period.day: "%Y-%m-%d",
    Period.month: "%Y-%m-01",
}
SQLITE_FORMATS = {
    Period.minute: "%Y-%m-%d %H:%M:00",
    Period.hour: "%Y-%m-%d %H:00:00",
    Period.day: "%Y-%m-%d",
    Period.month: "%Y-%m-01",
}


def _build_trunc_expression(db: AsyncSession, period: Period, column):
    dialect = db.bind.dialect.name

    """Builds the appropriate truncation SQL expression based on dialect and period."""
    if dialect == "postgresql":
        return func.date_trunc(period.value, column)
    elif dialect == "mysql":
        return func.date_format(column, MYSQL_FORMATS[period.value])
    elif dialect == "sqlite":
        return func.strftime(SQLITE_FORMATS[period.value], column)

    raise ValueError(f"Unsupported dialect: {dialect}")


def _parse_timezone_offset_to_seconds(offset_str: str) -> int:
    """
    Parse timezone offset string to seconds.

    Examples:
        '+03:30' -> 12600 seconds
        '-05:00' -> -18000 seconds
        'Z' or '+00:00' -> 0 seconds
    """
    import re

    # Handle 'Z' (UTC)
    if offset_str == "Z":
        return 0

    match = re.match(r"^([+-])(\d{2}):(\d{2})$", offset_str)
    if not match:
        raise ValueError(f"Invalid timezone offset format: {offset_str}")

    sign, hours, minutes = match.groups()
    total_seconds = int(hours) * 3600 + int(minutes) * 60
    return total_seconds if sign == "+" else -total_seconds


def _build_trunc_expression_tz(db: AsyncSession, period: Period, column, timezone_offset: str | None = None):
    """
    Builds timezone-aware truncation expression.

    Args:
        db: Database session
        period: Period to truncate to (minute, hour, day, month)
        column: Timestamp column to truncate
        timezone_offset: Timezone offset string (e.g., '+03:30', '-05:00')
                        If None, uses UTC (same as old behavior)

    Returns:
        SQLAlchemy expression for truncated timestamp in target timezone
    """
    dialect = db.bind.dialect.name

    if dialect == "postgresql":
        if timezone_offset:
            # Convert column to target timezone, then truncate
            return func.date_trunc(
                period.value, text(f"({column.key} AT TIME ZONE :tz)").bindparams(tz=timezone_offset)
            )
        else:
            return func.date_trunc(period.value, column)

    elif dialect == "mysql":
        if timezone_offset:
            # Convert from UTC to target timezone before formatting
            converted = func.convert_tz(column, "+00:00", timezone_offset)
            return func.date_format(converted, MYSQL_FORMATS[period.value])
        else:
            return func.date_format(column, MYSQL_FORMATS[period.value])

    elif dialect == "sqlite":
        if timezone_offset:
            # Calculate offset in seconds and adjust timestamp
            offset_seconds = _parse_timezone_offset_to_seconds(timezone_offset)
            adjusted = func.datetime(column, f"{offset_seconds:+d} seconds")
            return func.strftime(SQLITE_FORMATS[period.value], adjusted)
        else:
            return func.strftime(SQLITE_FORMATS[period.value], column)

    raise ValueError(f"Unsupported dialect: {dialect}")


def get_datetime_add_expression(db: AsyncSession, datetime_column, seconds: int):
    """
    Get database-specific datetime addition expression
    """
    dialect = db.bind.dialect.name
    if dialect == "mysql":
        return func.date_add(datetime_column, text("INTERVAL :seconds SECOND").bindparams(seconds=seconds))
    elif dialect == "postgresql":
        return datetime_column + func.make_interval(0, 0, 0, 0, 0, 0, seconds)
    elif dialect == "sqlite":
        return func.datetime(func.strftime("%s", datetime_column) + seconds, "unixepoch")

    raise ValueError(f"Unsupported dialect: {dialect}")


def json_extract(db: AsyncSession, column, path: str):
    """
    Args:
        column: The JSON column in your model
        path: JSON path (e.g., '$.theme')
    """
    dialect = db.bind.dialect.name
    match dialect:
        case "postgresql":
            keys = path.replace("$.", "").split(".")
            expr = column
            for key in keys:
                expr = expr.op("->>")(key) if key == keys[-1] else expr.op("->")(key)
            return expr.cast(String)
        case "mysql":
            return func.json_unquote(func.json_extract(column, path)).cast(String)
        case "sqlite":
            return func.json_extract(column, path).cast(String)


def build_json_proxy_settings_search_condition(db: AsyncSession, column, value: str):
    """
    Builds a condition to search JSON column for UUIDs or passwords.
    Supports PostgresSQL, MySQL, SQLite.
    """
    return or_(
        *[
            json_extract(db, column, field) == value
            for field in ("$.vmess.id", "$.vless.id", "$.trojan.password", "$.shadowsocks.password")
        ],
    )


async def get_system_usage(db: AsyncSession) -> System:
    """
    Retrieves system usage information.

    Args:
        db (AsyncSession): Database session.

    Returns:
        System: System usage information.
    """
    return (await db.execute(select(System))).scalar_one_or_none()


async def get_jwt_secret_key(db: AsyncSession) -> str:
    """
    Retrieves the JWT secret key.

    Args:
        db (AsyncSession): Database session.

    Returns:
        str: JWT secret key.
    """
    return (await db.execute(select(JWT))).scalar_one_or_none().secret_key
