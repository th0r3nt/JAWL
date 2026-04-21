from datetime import datetime, timezone, timedelta
from typing import Optional


def get_timezone(offset_hours: int) -> timezone:
    """Возвращает объект timezone со смещением в часах."""
    return timezone(timedelta(hours=offset_hours))


def get_now_formatted(offset_hours: int, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Возвращает текущее время в нужном часовом поясе."""
    tz = get_timezone(offset_hours)
    return datetime.now(tz).strftime(fmt)


def format_timestamp(
    timestamp: float, offset_hours: int, fmt: str = "%Y-%m-%d %H:%M:%S"
) -> str:
    """Форматирует UNIX-timestamp с учетом часового пояса."""
    tz = get_timezone(offset_hours)
    return datetime.fromtimestamp(timestamp, tz=tz).strftime(fmt)


def format_datetime(dt: datetime, offset_hours: int, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Применяет смещение к существующему объекту datetime и возвращает строку."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    tz = get_timezone(offset_hours)
    return dt.astimezone(tz).strftime(fmt)


def safe_format_timestamp(
    timestamp: Optional[float], offset_hours: int, fmt: str = "%Y-%m-%d %H:%M:%S"
) -> str:
    """Безопасно форматирует UNIX-timestamp, возвращая заглушку, если времени нет."""

    if not timestamp:
        return "Неизвестно"
    return format_timestamp(timestamp, offset_hours, fmt)


def seconds_to_duration_str(seconds: int | float) -> str:
    """Переводит секунды в формат (DD дней,) HH:MM:SS."""
    
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    days, hours = divmod(hours, 24)

    if days > 0:
        return f"{days} дней, {hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"
