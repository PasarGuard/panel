from datetime import datetime
from typing import Optional

from sqlalchemy import String, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import JWT, System
from app.models.stats import Period
from app.utils.helpers import fix_datetime_timezone, get_timezone_offset_string

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


def _build_trunc_expression(
    db: AsyncSession,
    period: Period,
    column,
    start: Optional[datetime] = None,
):
    """
    Builds the appropriate truncation SQL expression based on dialect and period.

    Args:
        db: Database session
        period: Time period for truncation (minute, hour, day, month)
        column: Database column to truncate
        start: Start datetime for timezone-aware grouping (uses its timezone if provided)

    Returns:
        SQL expression for truncation
    """
    dialect = db.bind.dialect.name

    # Calculate timezone offset if start datetime has timezone info
    offset_seconds = None
    if start and start.tzinfo:
        offset = start.tzinfo.utcoffset(start)
        if offset:
            offset_seconds = int(offset.total_seconds())

    if dialect == "postgresql":
        if start and start.tzinfo:
            # Convert timestamptz to target timezone, then truncate
            tz_str = get_timezone_offset_string(start)
            return func.date_trunc(period.value, column.op("AT TIME ZONE")(tz_str))
        return func.date_trunc(period.value, column)
    elif dialect == "mysql":
        if offset_seconds is not None:
            # Add offset before truncating
            adjusted_column = func.date_add(column, text(f"INTERVAL {offset_seconds} SECOND"))
            return func.date_format(adjusted_column, MYSQL_FORMATS[period.value])
        return func.date_format(column, MYSQL_FORMATS[period.value])
    elif dialect == "sqlite":
        if offset_seconds is not None:
            # Add offset before truncating
            adjusted_column = func.datetime(func.strftime("%s", column) + offset_seconds, "unixepoch")
            return func.strftime(SQLITE_FORMATS[period.value], adjusted_column)
        return func.strftime(SQLITE_FORMATS[period.value], column)

    raise ValueError(f"Unsupported dialect: {dialect}")


def _convert_period_start_timezone(row_dict: dict, target_tz, db: AsyncSession = None) -> None:
    """
    Convert period_start to target timezone if specified.

    For MySQL/SQLite, the offset is already applied in SQL, so period_start
    is already in the target timezone and should not be re-converted.
    For PostgreSQL, the offset is applied via AT TIME ZONE in SQL.

    Args:
        row_dict: Dictionary containing 'period_start' key
        target_tz: Reference timezone
        db: Database session to detect dialect (optional)
    """
    if "period_start" in row_dict:
        period_start = row_dict["period_start"]
        if period_start is not None and target_tz is not None:
            dialect = db.bind.dialect.name if db else "postgresql"

            if dialect in ("mysql", "sqlite"):
                # Offset already applied in SQL; period_start is naive but in target timezone
                # Just add the timezone info without converting
                if isinstance(period_start, str):
                    period_start = fix_datetime_timezone(period_start)
                row_dict["period_start"] = period_start.replace(tzinfo=target_tz)
            else:
                # PostgreSQL: AT TIME ZONE returns naive timestamp already in target timezone
                # Just attach timezone info without converting
                if isinstance(period_start, str):
                    period_start = fix_datetime_timezone(period_start)
                row_dict["period_start"] = period_start.replace(tzinfo=target_tz)


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
