"""
Utilities for Working with Time and Timezones.

Provides consistent formatting of dates, calculation of offsets,
and a human-readable representation of time intervals (uptime/duration).
Used across all framework layers for logging and context generation.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional


def get_timezone(offset_hours: int) -> timezone:
    """
    Returns a timezone object with the specified offset in hours relative to UTC.

    Args:
        offset_hours (int): Timezone offset (e.g., 3 for MSK, -5 for EST).

    Returns:
        timezone: The datetime timezone object.
    """

    return timezone(timedelta(hours=offset_hours))


def get_now_formatted(offset_hours: int, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    Returns the current date and time as a formatted string considering the timezone offset.

    Args:
        offset_hours (int): Timezone offset relative to UTC.
        fmt (str, optional): Date/time format string. Defaults to "%Y-%m-%d %H:%M:%S".

    Returns:
        str: Formatted string of the current time.
    """

    tz = get_timezone(offset_hours)
    return datetime.now(tz).strftime(fmt)


def format_timestamp(
    timestamp: float, offset_hours: int, fmt: str = "%Y-%m-%d %H:%M:%S"
) -> str:
    """
    Formats a UNIX timestamp into a readable string considering the system's timezone.

    Args:
        timestamp (float): UNIX timestamp in seconds.
        offset_hours (int): Timezone offset relative to UTC.
        fmt (str, optional): Formatting template. Defaults to "%Y-%m-%d %H:%M:%S".

    Returns:
        str: Formatted date/time string.
    """
    tz = get_timezone(offset_hours)
    return datetime.fromtimestamp(timestamp, tz=tz).strftime(fmt)


def format_datetime(dt: datetime, offset_hours: int, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    Applies the specified offset to an existing datetime object and returns a string.
    If the passed object is naive (no timezone info), it is strictly treated as UTC first.

    Args:
        dt (datetime): Source date/time object.
        offset_hours (int): Target timezone offset.
        fmt (str, optional): Formatting template. Defaults to "%Y-%m-%d %H:%M:%S".

    Returns:
        str: Formatted string with the applied timezone.
    """

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    tz = get_timezone(offset_hours)
    return dt.astimezone(tz).strftime(fmt)


def safe_format_timestamp(
    timestamp: Optional[float], offset_hours: int, fmt: str = "%Y-%m-%d %H:%M:%S"
) -> str:
    """
    Safe wrapper for formatting a UNIX timestamp.
    Guarantees no exceptions if a None value is passed.

    Args:
        timestamp (Optional[float]): UNIX timestamp in seconds or None.
        offset_hours (int): Timezone offset relative to UTC.
        fmt (str, optional): Formatting template. Defaults to "%Y-%m-%d %H:%M:%S".

    Returns:
        str: Formatted date/time, or the string "Unknown" if the timestamp is None.
    """

    if timestamp is None:
        return "Unknown"
    return format_timestamp(timestamp, offset_hours, fmt)


def _pluralize_days(n: int) -> str:
    """
    Determines the correct plural form of the word 'day' in English.

    Args:
        n (int): Number of days.

    Returns:
        str: "day" if n is 1, else "days".
    """
    return "day" if abs(n) == 1 else "days"


def seconds_to_duration_str(seconds: int | float) -> str:
    """
    Converts duration in seconds to a human-readable uptime format.
    Example output: "5 days, 12:04:30" or "01:15:00".

    Args:
        seconds (int | float): Total seconds.

    Returns:
        str: Formatted duration string.
    """
    total = max(int(seconds), 0)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    days, hours = divmod(hours, 24)

    if days > 0:
        return f"{days} {_pluralize_days(days)}, {hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"
