import pytest
import time
from unittest.mock import AsyncMock

from src.utils.event.registry import EventLevel
from src.l3_agent.heartbeat import Heartbeat


@pytest.fixture
def mock_react_loop():
    return AsyncMock()


def test_heartbeat_wake_up_high_critical(mock_react_loop):
    """Тест: HIGH/CRITICAL события моментально сбрасывают таймер и будят агента."""
    hb = Heartbeat(mock_react_loop, tick_interval_sec=60)
    hb._next_tick_time = time.time() + 60  # Должен спать еще 60 сек

    hb.wake_up(EventLevel.HIGH, "URGENT_EVENT", {"key": "value"})

    assert hb._wake_event.is_set()
    assert hb._wake_reason == "URGENT_EVENT"
    assert hb._wake_payload == {"key": "value"}
    assert hb._next_tick_time <= time.time()  # Время сна сброшено на 0


def test_heartbeat_wake_up_medium(mock_react_loop):
    """Тест: MEDIUM события сокращают время сна ровно наполовину."""
    hb = Heartbeat(mock_react_loop, tick_interval_sec=60)
    now = time.time()
    hb._next_tick_time = now + 60

    hb.wake_up(EventLevel.MEDIUM, "SOME_EVENT")

    assert hb._wake_event.is_set()
    # 60 / 2 = 30 секунд осталось
    expected_time = now + 30
    assert abs(hb._next_tick_time - expected_time) < 0.1


def test_heartbeat_wake_up_low(mock_react_loop):
    """Тест: LOW/BACKGROUND события незначительно (на 20%) сокращают время сна."""
    hb = Heartbeat(mock_react_loop, tick_interval_sec=60)
    now = time.time()
    hb._next_tick_time = now + 60

    hb.wake_up(EventLevel.BACKGROUND, "TRASH_EVENT")

    assert hb._wake_event.is_set()
    # 60 * 0.8 = 48 секунд осталось
    expected_time = now + 48
    assert abs(hb._next_tick_time - expected_time) < 0.1


@pytest.mark.asyncio
async def test_heartbeat_loop_proactivity(mock_react_loop):
    """
    Тест: если событий не было, Heartbeat должен проснуться по таймауту
    с причиной PROACTIVITY и вызвать ReactLoop.
    """
    hb = Heartbeat(mock_react_loop, tick_interval_sec=0)  # Мгновенный таймаут

    # Чтобы цикл не стал бесконечным, заставим ReactLoop остановить Heartbeat
    async def stop_hb(*args, **kwargs):
        hb.stop()

    mock_react_loop.run.side_effect = stop_hb

    await hb.start()

    mock_react_loop.run.assert_called_once_with(event_name="PROACTIVITY", payload={})


@pytest.mark.asyncio
async def test_heartbeat_loop_event_driven(mock_react_loop):
    """Тест: если пришло событие, Heartbeat передает его в ReactLoop."""
    hb = Heartbeat(mock_react_loop, tick_interval_sec=60)

    async def trigger_event_and_stop(*args, **kwargs):
        hb.stop()

    mock_react_loop.run.side_effect = trigger_event_and_stop

    # Имитируем, что событие пришло до старта цикла (чтобы мгновенно проснуться)
    hb.wake_up(EventLevel.CRITICAL, "DB_DOWN", {"error": "timeout"})

    await hb.start()

    mock_react_loop.run.assert_called_once_with(
        event_name="DB_DOWN", payload={"error": "timeout"}
    )
