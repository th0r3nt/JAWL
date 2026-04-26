from datetime import datetime, timezone
from src.utils.dtime import (
    get_now_formatted,
    format_timestamp,
    format_datetime,
    safe_format_timestamp,
    seconds_to_duration_str,
)


def test_get_now_formatted():
    now_str = get_now_formatted(offset_hours=3)
    assert len(now_str) == 19
    assert "-" in now_str and ":" in now_str


def test_format_timestamp():
    formatted = format_timestamp(1700000000, offset_hours=3)
    assert formatted == "2023-11-15 01:13:20"


def test_format_datetime():
    dt = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    formatted = format_datetime(dt, offset_hours=-5)
    assert formatted == "2023-01-01 07:00:00"


def test_safe_format_timestamp_none_returns_placeholder():
    assert safe_format_timestamp(None, offset_hours=0) == "Неизвестно"


def test_safe_format_timestamp_zero_is_valid():
    assert safe_format_timestamp(0, offset_hours=0) == "1970-01-01 00:00:00"


def test_seconds_to_duration_str_no_days():
    assert seconds_to_duration_str(0) == "00:00:00"
    assert seconds_to_duration_str(65) == "00:01:05"
    assert seconds_to_duration_str(3661) == "01:01:01"


def test_seconds_to_duration_str_pluralization():
    assert seconds_to_duration_str(86400).startswith("1 день,")
    assert seconds_to_duration_str(2 * 86400).startswith("2 дня,")
    assert seconds_to_duration_str(5 * 86400).startswith("5 дней,")
    assert seconds_to_duration_str(11 * 86400).startswith("11 дней,")
    assert seconds_to_duration_str(21 * 86400).startswith("21 день,")
    assert seconds_to_duration_str(22 * 86400).startswith("22 дня,")


def test_seconds_to_duration_str_negative_clamped():
    assert seconds_to_duration_str(-10) == "00:00:00"
