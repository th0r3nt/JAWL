"""
Утилиты для работы со временем и часовыми поясами.

Обеспечивают консистентное форматирование дат, вычисление смещений (timezone offsets)
и человекочитаемое представление временных интервалов (uptime).
Используются во всех слоях фреймворка для логирования и формирования контекста.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional


def get_timezone(offset_hours: int) -> timezone:
    """
    Возвращает объект timezone с заданным смещением в часах относительно UTC.

    Args:
        offset_hours (int): Смещение часового пояса (например, 3 для МСК, -5 для EST).

    Returns:
        timezone: Объект временной зоны datetime.
    """
    
    return timezone(timedelta(hours=offset_hours))


def get_now_formatted(offset_hours: int, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    Возвращает текущую дату и время в виде отформатированной строки с учетом часового пояса.

    Args:
        offset_hours (int): Смещение часового пояса относительно UTC.
        fmt (str, optional): Формат строки даты/времени. По умолчанию "%Y-%m-%d %H:%M:%S".

    Returns:
        str: Отформатированная строка текущего времени.
    """

    tz = get_timezone(offset_hours)
    return datetime.now(tz).strftime(fmt)


def format_timestamp(
    timestamp: float, offset_hours: int, fmt: str = "%Y-%m-%d %H:%M:%S"
) -> str:
    """
    Форматирует UNIX-timestamp в читаемую строку с учетом часового пояса системы.

    Args:
        timestamp (float): UNIX-время в секундах.
        offset_hours (int): Смещение часового пояса относительно UTC.
        fmt (str, optional): Шаблон форматирования. По умолчанию "%Y-%m-%d %H:%M:%S".

    Returns:
        str: Отформатированная строка даты/времени.

    """
    tz = get_timezone(offset_hours)
    return datetime.fromtimestamp(timestamp, tz=tz).strftime(fmt)


def format_datetime(dt: datetime, offset_hours: int, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    Применяет заданное смещение к существующему объекту datetime и возвращает строку.
    Если переданный объект наивный (без timezone), он принудительно трактуется как UTC.

    Args:
        dt (datetime): Исходный объект даты/времени.
        offset_hours (int): Требуемое смещение часового пояса.
        fmt (str, optional): Шаблон форматирования. По умолчанию "%Y-%m-%d %H:%M:%S".

    Returns:
        str: Отформатированная строка с примененным часовым поясом.
    """

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    tz = get_timezone(offset_hours)
    return dt.astimezone(tz).strftime(fmt)


def safe_format_timestamp(
    timestamp: Optional[float], offset_hours: int, fmt: str = "%Y-%m-%d %H:%M:%S"
) -> str:
    """
    Безопасная обертка для форматирования UNIX-timestamp.
    Гарантирует отсутствие исключений при передаче пустого значения (None).

    Args:
        timestamp (Optional[float]): UNIX-время в секундах или None.
        offset_hours (int): Смещение часового пояса относительно UTC.
        fmt (str, optional): Шаблон форматирования. По умолчанию "%Y-%m-%d %H:%M:%S".

    Returns:
        str: Отформатированное время или строка "Неизвестно", если timestamp равен None.
    """

    if timestamp is None:
        return "Неизвестно"
    return format_timestamp(timestamp, offset_hours, fmt)


def _pluralize_days(n: int) -> str:
    """
    Определяет правильное склонение слова "день" для русского языка на основе числа.

    Args:
        n (int): Количество дней.

    Returns:
        str: Одно из слов: "день", "дня", "дней".
    """
    mod100 = abs(n) % 100
    if 11 <= mod100 <= 14:
        return "дней"
    mod10 = mod100 % 10
    if mod10 == 1:
        return "день"
    if 2 <= mod10 <= 4:
        return "дня"
    return "дней"


def seconds_to_duration_str(seconds: int | float) -> str:
    """
    Переводит длительность в секундах в человекочитаемый формат аптайма.
    Пример вывода: "5 дней, 12:04:30" или "01:15:00".

    Args:
        seconds (int | float): Общее количество секунд.

    Returns:
        str: Отформатированная строка продолжительности времени.
    """
    total = max(int(seconds), 0)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    days, hours = divmod(hours, 24)

    if days > 0:
        return f"{days} {_pluralize_days(days)}, {hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"
