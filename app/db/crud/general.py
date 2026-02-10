from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import DateTime, String, cast, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import JWT, System
from app.models.stats import Period

MYSQL_FORMATS = {
    Period.minute: "%Y-%m-%d %H:%i:00",
    Period.hour: "%Y-%m-%d %H:00:00",
    Period.day: "%Y-%m-%d 00:00:00",
    Period.month: "%Y-%m-01 00:00:00",
}

SQLITE_FORMATS = {
    Period.minute: "%Y-%m-%d %H:%M:00",
    Period.hour: "%Y-%m-%d %H:00:00",
    Period.day: "%Y-%m-%d 00:00:00",
    Period.month: "%Y-%m-01 00:00:00",
}


def _build_trunc_expression(
    db: AsyncSession,
    period: Period,
    column,
    start: Optional[datetime] = None,
):
    """
    Builds the appropriate truncation SQL expression based on dialect and period.

    The correct approach for timezone-aware truncation is:
    1. Convert UTC timestamp to target timezone
    2. Truncate in the target timezone
    3. Return result as naive timestamp representing wall-clock time in target timezone

    Args:
        db: Database session
        period: Time period for truncation (minute, hour, day, month)
        column: Database column to truncate (assumed to be in UTC)
        start: Start datetime for timezone-aware grouping (uses its timezone if provided)

    Returns:
        SQL expression for truncation that returns naive timestamps/strings
        representing wall-clock time in the target timezone
    """
    dialect = db.bind.dialect.name

    # Extract timezone offset from start parameter
    tz_offset_str = None
    tz_offset_minutes = None

    if start and start.tzinfo:
        offset = start.tzinfo.utcoffset(start)
        if offset:
            total_seconds = int(offset.total_seconds())
            hours, remainder = divmod(abs(total_seconds), 3600)
            minutes = remainder // 60
            sign = "+" if total_seconds >= 0 else "-"
            # Format as +HH:MM or -HH:MM for PostgreSQL/MySQL
            tz_offset_str = f"{sign}{hours:02d}:{minutes:02d}"
            # Format as minutes for SQLite
            tz_offset_minutes = total_seconds // 60

    if dialect == "postgresql":
        if tz_offset_str:
            # Step 1: Treat column as UTC timestamp (converts timestamp -> timestamptz)
            utc_column = func.timezone("UTC", column)
            # Step 2: Convert to target timezone (converts timestamptz -> timestamp in target tz)
            adjusted_column = func.timezone(tz_offset_str, utc_column)
            # Step 3: Truncate in target timezone (stays as timestamp)
            truncated = func.date_trunc(period.value, adjusted_column)
            # Return the truncated timestamp (naive, representing wall-clock time in target tz)
            return truncated
        else:
            # No timezone specified, truncate as UTC
            return func.date_trunc(period.value, column)

    elif dialect == "mysql":
        if tz_offset_str:
            # Convert from UTC (+00:00) to target timezone
            adjusted_column = func.convert_tz(column, "+00:00", tz_offset_str)
            # DATE_FORMAT returns string representing wall-clock time in target timezone
            return func.date_format(adjusted_column, MYSQL_FORMATS[period])
        else:
            return func.date_format(column, MYSQL_FORMATS[period])

    elif dialect == "sqlite":
        if tz_offset_minutes is not None:
            # Apply timezone offset modifier, then format
            tz_modifier = f"{tz_offset_minutes:+d} minutes"
            adjusted_column = func.datetime(column, tz_modifier)
            # strftime returns string representing wall-clock time in target timezone
            return func.strftime(SQLITE_FORMATS[period], adjusted_column)
        else:
            return func.strftime(SQLITE_FORMATS[period], column)

    raise ValueError(f"Unsupported dialect: {dialect}")


def _get_next_period_boundary(dt: datetime, period: Period) -> datetime:
    """
    Get the next period boundary after (or at) the given datetime.

    This is used to find the first COMPLETE bucket to include when start time
    is not aligned to a period boundary.

    Args:
        dt: Datetime to find next boundary for
        period: Period to use for boundary calculation

    Returns:
        Datetime at the next period boundary (or same if already on boundary)

    Examples:
        >>> tehran_tz = timezone(timedelta(hours=3, minutes=30))
        >>> _get_next_period_boundary(
        ...     datetime(2026, 5, 9, 14, 2, 37, tzinfo=tehran_tz),
        ...     Period.hour
        ... )
        datetime(2026, 5, 9, 15, 0, 0, tzinfo=tehran_tz)

        >>> _get_next_period_boundary(
        ...     datetime(2026, 5, 9, 14, 0, 0, tzinfo=tehran_tz),
        ...     Period.hour
        ... )
        datetime(2026, 5, 9, 14, 0, 0, tzinfo=tehran_tz)
    """
    if period == Period.minute:
        # If any seconds/microseconds, round up to next minute
        if dt.second > 0 or dt.microsecond > 0:
            return dt.replace(second=0, microsecond=0) + timedelta(minutes=1)
        return dt.replace(second=0, microsecond=0)

    elif period == Period.hour:
        # If any minutes/seconds/microseconds, round up to next hour
        if dt.minute > 0 or dt.second > 0 or dt.microsecond > 0:
            return dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        return dt.replace(minute=0, second=0, microsecond=0)

    elif period == Period.day:
        # If any hours/minutes/seconds/microseconds, round up to next day
        if dt.hour > 0 or dt.minute > 0 or dt.second > 0 or dt.microsecond > 0:
            return dt.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)

    elif period == Period.month:
        # If not on first day or any time component, round up to next month
        if dt.day > 1 or dt.hour > 0 or dt.minute > 0 or dt.second > 0 or dt.microsecond > 0:
            # Go to first of next month
            if dt.month == 12:
                return datetime(dt.year + 1, 1, 1, 0, 0, 0, tzinfo=dt.tzinfo)
            else:
                return datetime(dt.year, dt.month + 1, 1, 0, 0, 0, tzinfo=dt.tzinfo)
        return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    return dt


def attach_timezone_to_period_start(row_dict: dict, target_tz, dialect: str = None) -> None:
    """
    Attach timezone info to period_start in the row dictionary.

    Handles both string and datetime types. If period_start is a string,
    it will be parsed to datetime first.

    Args:
        row_dict: Dictionary containing 'period_start' key
        target_tz: Timezone to attach to the period_start
        dialect: Database dialect name (for handling dialect-specific formats)
    """
    if "period_start" not in row_dict or row_dict["period_start"] is None or target_tz is None:
        return

    period_start = row_dict["period_start"]

    # If it's a string (SQLite or MySQL), parse it to datetime first
    if isinstance(period_start, str):
        # Remove any timezone suffix and parse
        clean_str = period_start.replace("Z", "").replace("+00:00", "").strip()
        try:
            # Try parsing with various formats
            for fmt in [
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M:00",
                "%Y-%m-%d %H:00:00",
                "%Y-%m-%d 00:00:00",
                "%Y-%m-01 00:00:00",
                "%Y-01-01 00:00:00",
            ]:
                try:
                    period_start = datetime.strptime(clean_str, fmt)
                    break
                except ValueError:
                    continue
            else:
                # Fallback to fromisoformat
                period_start = datetime.fromisoformat(clean_str)
        except (ValueError, AttributeError):
            # If parsing fails, leave as is
            return

    # If period_start is already timezone-aware, we MUST replace the timezone, NOT convert it.
    # Why? Because _build_trunc_expression returns a timestamp representing "Wall Clock Time"
    # in the target timezone.
    #
    # Example: 00:00 Tehran time.
    # Postgres SQL returns: 2026-02-10 00:00:00 (timestamp without time zone)
    #
    # However, some drivers/configurations might return this as a timezone-aware datetime (e.g. UTC).
    # If the driver returns "2026-02-10 00:00:00+00:00" (claiming it's midnight UTC),
    # using .astimezone(tehran_tz) would convert it to "03:30:00+03:30".
    #
    # But we KNOW the numerical value "00:00:00" is ALREADY the correct wall clock time.
    # So we must discard the driver's timezone assumption and stamp it with the correct timezone.
    if isinstance(period_start, datetime):
        # Always replace, never convert
        period_start = period_start.replace(tzinfo=target_tz)

        row_dict["period_start"] = period_start


def to_utc_for_filter(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Convert a timezone-aware datetime to UTC for database filtering.

    The database stores timestamps in UTC without timezone info. When filtering
    with timezone-aware datetimes, we need to convert them to UTC first.

    Args:
        dt: Timezone-aware datetime to convert

    Returns:
        UTC datetime without timezone info (naive), or None if input is None

    Example:
        >>> tehran_tz = timezone(timedelta(hours=3, minutes=30))
        >>> dt = datetime(2026, 2, 10, 0, 0, 0, tzinfo=tehran_tz)
        >>> to_utc_for_filter(dt)
        datetime(2026, 2, 9, 20, 30, 0)  # Naive UTC
    """
    if dt is None:
        return None

    # Convert to UTC
    if dt.tzinfo is not None:
        utc_dt = dt.astimezone(timezone.utc)
        # Return as naive datetime (remove tzinfo) for database comparison
        return utc_dt.replace(tzinfo=None)

    # Already naive, assume it's UTC
    return dt


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
