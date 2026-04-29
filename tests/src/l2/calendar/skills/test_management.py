import time
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch


@pytest.mark.asyncio
async def test_add_one_time_alarm(calendar_skills, calendar_client):
    """Тест: Создание разового будильника в будущем."""
    now = datetime.now(timezone(timedelta(hours=3)))
    future_time = now + timedelta(hours=1)
    time_str = future_time.strftime("%Y-%m-%d %H:%M")

    res = await calendar_skills.add_one_time_alarm(title="Task 1", datetime_str=time_str)

    assert res.is_success is True

    events = calendar_client.get_all_events()
    assert len(events) == 1
    assert events[0]["type"] == "one_time"
    assert events[0]["trigger_at"] > time.time()


@pytest.mark.asyncio
async def test_add_one_time_alarm_past_fails(calendar_skills):
    """Тест: Агент не должен ставить будильник в прошлое."""
    past_time_str = "2000-01-01 12:00"
    res = await calendar_skills.add_one_time_alarm("Old Task", past_time_str)

    assert res.is_success is False
    assert "уже в прошлом" in res.message


@pytest.mark.asyncio
async def test_add_interval_alarm(calendar_skills, calendar_client):
    """Тест: Создание интервального таймера."""
    res = await calendar_skills.add_interval_alarm(title="Ping", interval_minutes=30)

    assert res.is_success is True

    events = calendar_client.get_all_events()
    assert len(events) == 1
    assert events[0]["type"] == "interval"
    assert events[0]["interval_minutes"] == 30


@pytest.mark.asyncio
@patch("src.l2_interfaces.calendar.skills.management.datetime")
async def test_add_recurring_alarm_today(mock_datetime, calendar_skills, calendar_client):
    """Тест: Если указанное время сегодня еще не наступило, ставим будильник на сегодня."""
    tz = calendar_skills.tz
    mock_now = datetime(2024, 5, 1, 10, 0, tzinfo=tz)
    mock_datetime.now.return_value = mock_now
    mock_datetime.strptime = datetime.strptime
    mock_datetime.combine = datetime.combine

    res = await calendar_skills.add_recurring_alarm(
        title="Daily Meet", time_str="15:00", interval_days=1
    )

    assert res.is_success is True

    events = calendar_client.get_all_events()
    trigger_dt = datetime.fromtimestamp(events[0]["trigger_at"], tz=tz)

    assert trigger_dt.day == 1
    assert trigger_dt.hour == 15


@pytest.mark.asyncio
@patch("src.l2_interfaces.calendar.skills.management.datetime")
async def test_add_recurring_alarm_tomorrow(mock_datetime, calendar_skills, calendar_client):
    """Тест: Если указанное время сегодня уже прошло, переносим на завтра."""
    tz = calendar_skills.tz
    mock_now = datetime(2024, 5, 1, 20, 0, tzinfo=tz)
    mock_datetime.now.return_value = mock_now
    mock_datetime.strptime = datetime.strptime
    mock_datetime.combine = datetime.combine

    res = await calendar_skills.add_recurring_alarm(
        title="Daily Meet", time_str="15:00", interval_days=1
    )

    assert res.is_success is True

    events = calendar_client.get_all_events()
    trigger_dt = datetime.fromtimestamp(events[0]["trigger_at"], tz=tz)

    assert trigger_dt.day == 2
    assert trigger_dt.hour == 15


@pytest.mark.asyncio
async def test_delete_alarm(calendar_skills, calendar_client):
    """Тест: Успешное удаление будильника."""
    # Добавили обязательные поля, чтобы сортировка в клиенте не падала
    calendar_client.add_event(
        {
            "id": "event_123",
            "title": "To Delete",
            "type": "one_time",
            "trigger_at": time.time() + 1000,
        }
    )
    res = await calendar_skills.delete_alarm("event_12")

    assert res.is_success is True
    assert len(calendar_client.get_all_events()) == 0
