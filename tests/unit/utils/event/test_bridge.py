"""
Unit-тесты для моста маршрутизации событий (EventBridge).

Проверяют, что мост корректно подписывает ядро (Heartbeat) на шину событий,
обрабатывает команды выключения системы и обновляет конфигурацию на лету.
"""

import pytest
from unittest.mock import MagicMock

from src.system.container import SystemContainer
from src.utils.event.bridge import EventBridge
from src.utils.event.registry import Events


@pytest.fixture
def mock_container() -> SystemContainer:
    container_mock = MagicMock(spec=SystemContainer)
    container_mock.event_bus = MagicMock()
    container_mock.heartbeat = MagicMock()

    container_mock.sql = MagicMock()
    container_mock.sql.update_limits = MagicMock()
    container_mock.sql.update_context_depth = MagicMock()

    container_mock.dashboard_state = MagicMock()
    container_mock.dashboard_state.update_block = MagicMock()

    container_mock.exit_code = 0
    return container_mock


def test_bridge_setup_routing_subscriptions(mock_container: SystemContainer) -> None:
    """Тест: EventBridge подписывает обработчики на все события из реестра."""
    bridge = EventBridge(mock_container)
    bridge.setup_routing()

    assert mock_container.event_bus.subscribe.call_count > 10


@pytest.mark.asyncio
async def test_bridge_handler_triggers_heartbeat(mock_container: SystemContainer) -> None:
    """Тест: Базовый обработчик пробрасывает события в Heartbeat."""
    bridge = EventBridge(mock_container)

    handler = bridge._create_heartbeat_handler(Events.TELETHON_MESSAGE_INCOMING)
    await handler(message="Test", chat_id=123)

    mock_container.heartbeat.answer_to_event.assert_called_once()
    kwargs = mock_container.heartbeat.answer_to_event.call_args[1]

    assert kwargs["level"] == Events.TELETHON_MESSAGE_INCOMING.level
    assert kwargs["event_name"] == Events.TELETHON_MESSAGE_INCOMING.name
    assert kwargs["payload"]["message"] == "Test"


@pytest.mark.asyncio
async def test_bridge_shutdown_and_reboot(mock_container: SystemContainer) -> None:
    """Тест: Обработка критических сигналов на выключение и перезагрузку."""
    bridge = EventBridge(mock_container)

    # Тест выключения
    await bridge._handle_shutdown()
    assert mock_container.exit_code == 0
    assert mock_container.heartbeat.stop.call_count == 1

    # Тест перезагрузки
    await bridge._handle_reboot()
    assert mock_container.exit_code == 1
    assert mock_container.heartbeat.stop.call_count == 2


@pytest.mark.asyncio
async def test_bridge_config_update(mock_container: SystemContainer) -> None:
    """Тест: Изменение конфигурации на лету правильно делегируется модулям (Law of Demeter)."""
    bridge = EventBridge(mock_container)

    # Агент меняет лимит
    await bridge._handle_config_update(key="db_limit", module="tasks", value=42)
    mock_container.sql.update_limits.assert_called_once_with("tasks", 42)

    # Агент меняет память
    await bridge._handle_config_update(
        key="context_depth", high_ticks=5, medium_ticks=10, low_ticks=15
    )
    mock_container.sql.update_context_depth.assert_called_once_with(5, 10, 15)

    # Агент меняет пульс
    await bridge._handle_config_update(key="heartbeat_interval", value=300)
    mock_container.heartbeat.update_config.assert_called_once_with("heartbeat_interval", 300)


@pytest.mark.asyncio
async def test_bridge_dashboard_update(mock_container: SystemContainer) -> None:
    """Тест: Мост корректно обновляет кастомный дашборд."""
    bridge = EventBridge(mock_container)

    await bridge._handle_dashboard_update(name="Stats", content="CPU: 10%")
    mock_container.dashboard_state.update_block.assert_called_once_with("Stats", "CPU: 10%")
