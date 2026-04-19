from datetime import datetime, timezone
from src.utils.dtime import get_now_formatted, format_timestamp, format_datetime


def test_get_now_formatted():
    now_str = get_now_formatted(offset_hours=3)
    # Формат %Y-%m-%d %H:%M:%S всегда 19 символов
    assert len(now_str) == 19
    assert "-" in now_str and ":" in now_str


def test_format_timestamp():
    # 1700000000 = 2023-11-14 22:13:20 (UTC)
    # Смещение +3 часа -> 2023-11-15 01:13:20
    formatted = format_timestamp(1700000000, offset_hours=3)
    assert formatted == "2023-11-15 01:13:20"


def test_format_datetime():
    dt = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    # Смещение -5 часов
    formatted = format_datetime(dt, offset_hours=-5)
    assert formatted == "2023-01-01 07:00:00"
