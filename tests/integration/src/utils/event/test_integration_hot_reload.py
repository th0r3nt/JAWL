import pytest
import asyncio
from unittest.mock import MagicMock

from src.main import System
from src.utils.event.bus import EventBus
from src.utils.event.bridge import EventBridge
from src.utils.event.registry import Events
from src.utils.settings import SettingsConfig, InterfacesConfig


@pytest.mark.asyncio
async def test_integration_hot_reload_architecture():
    """
    Интеграционный тест: "Горячая перезагрузка конфигурации".
    Проверяет, что когда агент меняет настройки через Meta-интерфейс,
    EventBridge корректно маршрутизирует событие и модифицирует
    переменные работающих объектов (Heartbeat, SQLManager) прямо в оперативной памяти.
    """

    # 1. ПОДГОТОВКА СИСТЕМЫ
    bus = EventBus()
    settings = SettingsConfig()
    interfaces = InterfacesConfig()

    system = System(event_bus=bus, settings_config=settings, interfaces_config=interfaces)

    # Настраиваем SQL (Используем MagicMock, так как свойства синхронные)
    system.sql = MagicMock()
    system.sql.tasks = MagicMock()
    system.sql.tasks.max_tasks = 10  # Начальный лимит

    system.sql.ticks = MagicMock()
    system.sql.ticks.ticks_limit = 15
    system.sql.ticks.detailed_ticks = 3

    # Настраиваем Heartbeat
    system.heartbeat = MagicMock()
    system.heartbeat.update_config = MagicMock()

    # 2. ПОДНИМАЕМ МОСТ СОБЫТИЙ (EventBridge)
    bridge = EventBridge(system)
    bridge.setup_routing()

    # 3. ЭМУЛЯЦИЯ ИЗМЕНЕНИЯ НАСТРОЕК АГЕНТОМ (Meta Configurator)

    # Агент меняет лимит задач
    await bus.publish(Events.SYSTEM_CONFIG_UPDATED, key="db_limit", module="tasks", value=99)

    # Агент меняет глубину памяти
    await bus.publish(
        Events.SYSTEM_CONFIG_UPDATED, key="context_depth", total_ticks=50, detailed_ticks=10
    )

    # Агент меняет ритм пульса
    await bus.publish(Events.SYSTEM_CONFIG_UPDATED, key="heartbeat_interval", value=120)

    # Ждем, пока шина отработает все асинхронные обработчики моста
    if bus.background_tasks:
        await asyncio.gather(*bus.background_tasks)

    # 4. ПРОВЕРКА МУТАЦИЙ

    # SQL Manager должен был обновить лимиты на лету
    assert system.sql.tasks.max_tasks == 99
    assert system.sql.ticks.ticks_limit == 50
    assert system.sql.ticks.detailed_ticks == 10

    # Heartbeat должен был получить сигнал на обновление
    system.heartbeat.update_config.assert_called_once_with("heartbeat_interval", 120)