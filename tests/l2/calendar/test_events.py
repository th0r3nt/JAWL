import time
import pytest
from unittest.mock import patch
from src.utils.event.registry import Events


@pytest.mark.asyncio
async def test_events_polling_triggers(calendar_events, calendar_client, mock_bus):
    """
    Тест: Проверка логики цикла поллинга.
    - Разовые события удаляются.
    - Интервальные обновляют trigger_at.
    """
    now = time.time()

    calendar_client.add_event(
        {"id": "1", "title": "Past One Time", "type": "one_time", "trigger_at": now - 10}
    )
    calendar_client.add_event(
        {
            "id": "2",
            "title": "Past Interval",
            "type": "interval",
            "trigger_at": now - 10,
            "interval_minutes": 10,
        }
    )
    calendar_client.add_event(
        {"id": "3", "title": "Future Event", "type": "one_time", "trigger_at": now + 100}
    )

    calendar_events._is_running = True

    async def fake_sleep(*args, **kwargs):
        calendar_events._is_running = False

    with patch("asyncio.sleep", side_effect=fake_sleep):
        await calendar_events._loop()

    assert mock_bus.publish.call_count == 2
    call_args = mock_bus.publish.call_args_list
    assert call_args[0][0][0] == Events.SYSTEM_CALENDAR_ALARM

    events = calendar_client.get_all_events()
    assert len(events) == 2

    assert events[0]["id"] == "2"
    assert events[0]["trigger_at"] > now

    assert events[1]["id"] == "3"
