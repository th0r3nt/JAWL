import pytest
import time
from unittest.mock import AsyncMock

from src.utils.event.registry import EventLevel
from src.l3_agent.heartbeat import Heartbeat
from src.utils.settings import EventAccelerationConfig


@pytest.fixture
def mock_react_loop():
    return AsyncMock()


@pytest.fixture
def mock_accel_config():
    return EventAccelerationConfig(
        critical_multiplier=0.0,
        high_multiplier=0.3,
        medium_multiplier=0.6,
        low_multiplier=0.7,
        background_multiplier=0.8,
    )


def test_heartbeat_answer_to_event_high_critical(mock_react_loop, mock_accel_config):
    hb = Heartbeat(
        mock_react_loop,
        heartbeat_interval=60,
        continuous_cycle=False,
        accel_config=mock_accel_config,
        timezone=3,
    )
    hb._next_tick_time = time.time() + 60
    hb.answer_to_event(EventLevel.CRITICAL, "URGENT_EVENT", {"key": "value"})

    assert hb._wake_event.is_set()
    assert hb._wake_reason == "URGENT_EVENT"
    assert hb._wake_payload == {"key": "value"}


def test_heartbeat_answer_to_event_medium(mock_react_loop, mock_accel_config):
    hb = Heartbeat(
        mock_react_loop,
        heartbeat_interval=60,
        continuous_cycle=False,
        accel_config=mock_accel_config,
        timezone=3,
    )
    now = time.time()
    hb._next_tick_time = now + 60
    hb.answer_to_event(EventLevel.MEDIUM, "SOME_EVENT")
    expected_time = now + 36  # 60 * 0.6 = 36
    assert abs(hb._next_tick_time - expected_time) < 0.1


def test_heartbeat_answer_to_event_low(mock_react_loop, mock_accel_config):
    hb = Heartbeat(
        mock_react_loop,
        heartbeat_interval=60,
        continuous_cycle=False,
        accel_config=mock_accel_config,
        timezone=3,
    )
    now = time.time()
    hb._next_tick_time = now + 60
    hb.answer_to_event(EventLevel.BACKGROUND, "TRASH_EVENT")
    expected_time = now + 48  # 60 * 0.8 = 48
    assert abs(hb._next_tick_time - expected_time) < 0.1


@pytest.mark.asyncio
async def test_heartbeat_loop_heartbeat(mock_react_loop, mock_accel_config):
    hb = Heartbeat(
        mock_react_loop,
        heartbeat_interval=0,
        continuous_cycle=False,
        accel_config=mock_accel_config,
        timezone=3,
    )

    async def stop_hb(*args, **kwargs):
        hb.stop()

    mock_react_loop.run.side_effect = stop_hb
    await hb.start()
    mock_react_loop.run.assert_called_once_with(
        event_name="HEARTBEAT", payload={}, missed_events=[]
    )


@pytest.mark.asyncio
async def test_heartbeat_loop_event_driven(mock_react_loop, mock_accel_config):
    hb = Heartbeat(
        mock_react_loop,
        heartbeat_interval=60,
        continuous_cycle=False,
        accel_config=mock_accel_config,
        timezone=3,
    )

    async def trigger_event_and_stop(*args, **kwargs):
        hb.stop()

    mock_react_loop.run.side_effect = trigger_event_and_stop

    # Это событие попадет в память сна
    hb.answer_to_event(EventLevel.CRITICAL, "DB_DOWN", {"error": "timeout"})

    await hb.start()

    from unittest.mock import ANY

    mock_react_loop.run.assert_called_once_with(
        event_name="DB_DOWN", payload={"error": "timeout"}, missed_events=ANY
    )


def test_heartbeat_update_config(mock_react_loop, mock_accel_config):
    """Тест: обновление конфигурации на лету."""
    hb = Heartbeat(
        mock_react_loop,
        heartbeat_interval=60,
        continuous_cycle=False,
        accel_config=mock_accel_config,
        timezone=3,
    )

    # Меняем интервал
    hb.update_config("heartbeat_interval", 120)
    assert hb.heartbeat_interval == 120

    # Меняем continuous_cycle
    hb.update_config("continuous_cycle", True)
    assert hb.continuous_cycle is True


def test_heartbeat_priority_overwriting(mock_react_loop, mock_accel_config):
    """Тест: Heartbeat корректно обновляет причину пробуждения в зависимости от приоритета события."""
    hb = Heartbeat(
        mock_react_loop,
        heartbeat_interval=60,
        continuous_cycle=False,
        accel_config=mock_accel_config,
        timezone=3,
    )
    # Ставим очень маленькое оставшееся время сна (0.015 сек), чтобы любое событие
    # при умножении на множитель давало < 0.01 и вызывало экстренное пробуждение.
    hb._next_tick_time = time.time() + 0.015

    # 1. Прилетает MEDIUM событие (0.015 * 0.6 = 0.009 <= 0.01). Триггерит экстренное пробуждение.
    hb.answer_to_event(EventLevel.MEDIUM, "MEDIUM_EVENT")
    assert hb._wake_level == EventLevel.MEDIUM.value
    assert hb._wake_reason == "MEDIUM_EVENT"

    # 2. Во время сна прилетает CRITICAL (множитель 0.0, он важнее, должен перезаписать причину)
    hb.answer_to_event(EventLevel.CRITICAL, "CRITICAL_EVENT")
    assert hb._wake_level == EventLevel.CRITICAL.value
    assert hb._wake_reason == "CRITICAL_EVENT"

    # 3. Следом прилетает фоновый спам LOW (НЕ должен переписать важную причину, т.к. 20 < 50)
    hb.answer_to_event(EventLevel.LOW, "LOW_EVENT")
    assert hb._wake_level == EventLevel.CRITICAL.value
    assert hb._wake_reason == "CRITICAL_EVENT"
