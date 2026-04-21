import time
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

from src.l0_state.interfaces.state import CalendarState
from src.utils.event.bus import EventBus
from src.utils.event.registry import Events

from src.l2_interfaces.calendar.client import CalendarClient
from src.l2_interfaces.calendar.events import CalendarEvents
from src.l2_interfaces.calendar.skills.management import CalendarManagement


# ===================================================================
# FIXTURES
# ===================================================================


@pytest.fixture
def calendar_state():
    return CalendarState()


@pytest.fixture
def calendar_client(tmp_path: Path, calendar_state):
    """Изолированный клиент с временной папкой вместо реальной базы."""
    return CalendarClient(state=calendar_state, data_dir=tmp_path, timezone=3)


@pytest.fixture
def mock_bus():
    """Мок шины событий."""
    bus = MagicMock(spec=EventBus)
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def calendar_events(calendar_client, calendar_state, mock_bus):
    """Слушатель событий."""
    return CalendarEvents(
        client=calendar_client,
        state=calendar_state,
        event_bus=mock_bus,
        polling_interval=15,
    )


@pytest.fixture
def calendar_skills(calendar_client):
    """Навыки для агента."""
    return CalendarManagement(client=calendar_client)


# ===================================================================
# TESTS: CLIENT (JSON CRUD)
# ===================================================================


def test_client_init_creates_file(calendar_client):
    """Тест: При запуске клиент должен создать пустой JSON, если его нет."""
    assert calendar_client.filepath.exists()
    assert calendar_client.get_all_events() == []


def test_client_add_and_update(calendar_client):
    """Тест: Сохранение и перезапись списка событий."""
    dummy_event = {"id": "123", "title": "Test", "type": "one_time", "trigger_at": 1000.0}

    calendar_client.add_event(dummy_event)
    events = calendar_client.get_all_events()

    assert len(events) == 1
    assert events[0]["title"] == "Test"

    dummy_event["title"] = "Updated Test"
    calendar_client.update_events([dummy_event])

    assert calendar_client.get_all_events()[0]["title"] == "Updated Test"


# ===================================================================
# TESTS: SKILLS (Management)
# ===================================================================


@pytest.mark.asyncio
async def test_add_one_time_alarm(calendar_skills, calendar_client):
    """Тест: Создание разового будильника в будущем."""
    # Берем время + 1 час от текущего с учетом часового пояса +3
    now = datetime.now(timezone(timedelta(hours=3)))
    future_time = now + timedelta(hours=1)
    time_str = future_time.strftime("%Y-%m-%d %H:%M")

    res = await calendar_skills.add_one_time_alarm(title="Task 1", datetime_str=time_str)

    assert res.is_success is True

    events = calendar_client.get_all_events()
    assert len(events) == 1
    assert events[0]["type"] == "one_time"
    assert events[0]["title"] == "Task 1"
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

    # Мокаем текущее время как "10:00"
    mock_now = datetime(2024, 5, 1, 10, 0, tzinfo=tz)
    mock_datetime.now.return_value = mock_now
    mock_datetime.strptime = datetime.strptime
    mock_datetime.combine = datetime.combine

    # Ставим будильник на "15:00"
    res = await calendar_skills.add_recurring_alarm(
        title="Daily Meet", time_str="15:00", interval_days=1
    )

    assert res.is_success is True

    events = calendar_client.get_all_events()
    trigger_dt = datetime.fromtimestamp(events[0]["trigger_at"], tz=tz)

    assert trigger_dt.day == 1  # Должен сработать сегодня
    assert trigger_dt.hour == 15


@pytest.mark.asyncio
@patch("src.l2_interfaces.calendar.skills.management.datetime")
async def test_add_recurring_alarm_tomorrow(mock_datetime, calendar_skills, calendar_client):
    """Тест: Если указанное время сегодня уже прошло, переносим на завтра (по interval_days)."""
    tz = calendar_skills.tz

    # Мокаем текущее время как "20:00"
    mock_now = datetime(2024, 5, 1, 20, 0, tzinfo=tz)
    mock_datetime.now.return_value = mock_now
    mock_datetime.strptime = datetime.strptime
    mock_datetime.combine = datetime.combine

    # Ставим будильник на "15:00"
    res = await calendar_skills.add_recurring_alarm(
        title="Daily Meet", time_str="15:00", interval_days=1
    )

    assert res.is_success is True

    events = calendar_client.get_all_events()
    trigger_dt = datetime.fromtimestamp(events[0]["trigger_at"], tz=tz)

    assert trigger_dt.day == 2  # Должен сработать завтра
    assert trigger_dt.hour == 15


@pytest.mark.asyncio
async def test_delete_alarm(calendar_skills, calendar_client):
    """Тест: Успешное удаление будильника."""
    calendar_client.add_event({"id": "event_123", "title": "To Delete"})

    # Удаление по началу ID
    res = await calendar_skills.delete_alarm("event_12")

    assert res.is_success is True
    assert len(calendar_client.get_all_events()) == 0


# ===================================================================
# TESTS: EVENTS (Polling)
# ===================================================================


@pytest.mark.asyncio
async def test_events_polling_triggers(calendar_events, calendar_client, mock_bus):
    """
    Тест: Проверка логики цикла поллинга.
    Сработавшие события должны отправить сигнал в EventBus.
    - Разовые события удаляются.
    - Интервальные/повторяющиеся обновляют trigger_at.
    """
    now = time.time()

    # 1. Просроченное разовое (должно удалиться)
    calendar_client.add_event(
        {"id": "1", "title": "Past One Time", "type": "one_time", "trigger_at": now - 10}
    )
    # 2. Просроченное интервальное (должно обновиться)
    calendar_client.add_event(
        {
            "id": "2",
            "title": "Past Interval",
            "type": "interval",
            "trigger_at": now - 10,
            "interval_minutes": 10,
        }
    )
    # 3. Будущее событие (не должно трогаться)
    calendar_client.add_event(
        {"id": "3", "title": "Future Event", "type": "one_time", "trigger_at": now + 100}
    )

    calendar_events._is_running = True

    # Мокаем asyncio.sleep, чтобы после первой итерации прервать цикл (иначе зависнет навечно)
    async def fake_sleep(*args, **kwargs):
        calendar_events._is_running = False

    with patch("asyncio.sleep", side_effect=fake_sleep):
        await calendar_events._loop()

    # Проверки
    # Ожидаем 2 вызова publish (для событий #1 и #2)
    assert mock_bus.publish.call_count == 2

    call_args = mock_bus.publish.call_args_list
    assert call_args[0][0][0] == Events.SYSTEM_CALENDAR_ALARM

    # Проверяем обновленный JSON
    events = calendar_client.get_all_events()
    assert len(events) == 2  # Одно разовое было удалено

    assert events[0]["id"] == "2"  # Интервальное осталось
    assert events[0]["trigger_at"] > now  # Время сдвинулось вперед (текущее время + 10 минут)

    assert events[1]["id"] == "3"  # Будущее осталось нетронутым
