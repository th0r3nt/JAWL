from datetime import datetime, timezone, timedelta


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
