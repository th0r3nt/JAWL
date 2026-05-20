import pytest
import asyncio
from unittest.mock import MagicMock

from src.system.container import SystemContainer
from src.utils.event.bus import EventBus
from src.utils.event.bridge import EventBridge
from src.utils.event.registry import Events
from src.utils.settings import SettingsConfig, InterfacesConfig


@pytest.mark.asyncio
async def test_integration_hot_reload_architecture():
    """
    Интеграционный тест: "Горячая перезагрузка конфигурации".
    Проверяет, что когда агент меняет настройки через Meta-интерфейс,
    EventBridge корректно маршрутизирует событие и вызывает методы
    соответствующих систем.
    """

    bus = EventBus()
    settings = SettingsConfig()
    interfaces = InterfacesConfig()

    container = SystemContainer(settings=settings, interfaces_config=interfaces, event_bus=bus)

    # Мокаем целевые системы (SQL и Heartbeat)
    container.sql = MagicMock()
    container.sql.update_limits = MagicMock()
    container.sql.update_context_depth = MagicMock()

    container.heartbeat = MagicMock()
    container.heartbeat.update_config = MagicMock()

    # ПОДНИМАЕМ МОСТ СОБЫТИЙ
    bridge = EventBridge(container)
    bridge.setup_routing()

    # ЭМУЛЯЦИЯ ИЗМЕНЕНИЯ НАСТРОЕК АГЕНТОМ (Meta Configurator)
    await bus.publish(Events.SYSTEM_CONFIG_UPDATED, key="db_limit", module="tasks", value=99)

    await bus.publish(
        Events.SYSTEM_CONFIG_UPDATED,
        key="context_depth",
        high_ticks=5,
        medium_ticks=10,
        low_ticks=35,
    )

    await bus.publish(Events.SYSTEM_CONFIG_UPDATED, key="heartbeat_interval", value=120)

    # Ждем, пока шина отработает все асинхронные обработчики моста
    if bus.background_tasks:
        await asyncio.gather(*bus.background_tasks)

    # ПРОВЕРКА МУТАЦИЙ
    container.sql.update_limits.assert_called_once_with("tasks", 99)
    container.sql.update_context_depth.assert_called_once_with(5, 10, 35)
    container.heartbeat.update_config.assert_called_once_with("heartbeat_interval", 120)
