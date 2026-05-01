"""
Unit-тесты для моста маршрутизации событий (EventBridge).

Проверяют, что мост корректно подписывает ядро (Heartbeat) на шину событий,
обрабатывает команды выключения системы и обновляет конфигурацию на лету.
"""

import pytest
from unittest.mock import MagicMock

from src.main import System
from src.utils.event.bridge import EventBridge
from src.utils.event.registry import Events


@pytest.fixture
def mock_system() -> System:
    sys_mock = MagicMock(spec=System)
    sys_mock.event_bus = MagicMock()
    sys_mock.heartbeat = MagicMock()

    # ИСПОЛЬЗУЕМ ПРОСТЫЕ КЛАССЫ (DUMMY), ЧТОБЫ ИЗБЕЖАТЬ ПЕРЕХВАТА АТРИБУТОВ МОКАМИ
    class DummySQL:
        pass

    class DummyTasks:
        max_tasks = 10

    class DummyTicks:
        ticks_limit = 10
        detailed_ticks = 2

    sys_mock.sql = DummySQL()
    sys_mock.sql.tasks = DummyTasks()
    sys_mock.sql.ticks = DummyTicks()

    sys_mock.dashboard_state = MagicMock()
    sys_mock._exit_code = 0
    return sys_mock


def test_bridge_setup_routing_subscriptions(mock_system: System) -> None:
    """Тест: EventBridge подписывает обработчики на все события из реестра."""
    bridge = EventBridge(mock_system)
    bridge.setup_routing()

    # Убеждаемся, что метод subscribe вызывался (он подписывает на каждое событие)
    assert mock_system.event_bus.subscribe.call_count > 10


@pytest.mark.asyncio
async def test_bridge_handler_triggers_heartbeat(mock_system: System) -> None:
    """Тест: Базовый обработчик пробрасывает события в Heartbeat."""
    bridge = EventBridge(mock_system)
    bridge.setup_routing()

    # Находим зарегистрированный базовый обработчик (не системный)
    call_args = mock_system.event_bus.subscribe.call_args_list

    # Имитируем срабатывание подписки
    for call in call_args:
        event_obj, handler = call[0]
        if event_obj.name == Events.TELETHON_MESSAGE_INCOMING.name:
            await handler(message="Test", chat_id=123)
            break

    mock_system.heartbeat.answer_to_event.assert_called_once()
    kwargs = mock_system.heartbeat.answer_to_event.call_args[1]
    assert kwargs["level"] == Events.TELETHON_MESSAGE_INCOMING.level
    assert kwargs["event_name"] == Events.TELETHON_MESSAGE_INCOMING.name
    assert kwargs["payload"]["message"] == "Test"


@pytest.mark.asyncio
async def test_bridge_shutdown_and_reboot(mock_system: System) -> None:
    """Тест: Обработка критических сигналов на выключение и перезагрузку."""
    bridge = EventBridge(mock_system)
    bridge.setup_routing()

    # Находим обработчики
    shutdown_handler = None
    reboot_handler = None
    for call in mock_system.event_bus.subscribe.call_args_list:
        if call[0][0].name == Events.SYSTEM_SHUTDOWN_REQUESTED.name:
            shutdown_handler = call[0][1]
        elif call[0][0].name == Events.SYSTEM_REBOOT_REQUESTED.name:
            reboot_handler = call[0][1]

    # Тест выключения
    await shutdown_handler()
    assert mock_system._exit_code == 0
    assert mock_system.heartbeat.stop.call_count == 1

    # Тест перезагрузки
    await reboot_handler()
    assert mock_system._exit_code == 1
    assert mock_system.heartbeat.stop.call_count == 2


@pytest.mark.asyncio
async def test_bridge_config_update(mock_system: System) -> None:
    """Тест: Изменение конфигурации на лету."""
    bridge = EventBridge(mock_system)
    bridge.setup_routing()

    config_handlers = []
    for call in mock_system.event_bus.subscribe.call_args_list:
        if call[0][0].name == Events.SYSTEM_CONFIG_UPDATED.name:
            config_handlers.append(call[0][1])

    # ИСПРАВЛЕНИЕ: Вызываем ВСЕ найденные хендлеры.
    # Один из них пробросит событие в Heartbeat, а второй изменит конфиги БД.
    for handler in config_handlers:
        await handler(key="db_limit", module="tasks", value=42)
        await handler(key="context_depth", total_ticks=20, detailed_ticks=5)

    assert mock_system.sql.tasks.max_tasks == 42
    assert mock_system.sql.ticks.ticks_limit == 20
