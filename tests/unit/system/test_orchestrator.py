import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.system.container import SystemContainer
from src.system.orchestrator import SystemOrchestrator
from src.utils.settings import SettingsConfig, InterfacesConfig
from src.utils.event.bus import EventBus


@pytest.fixture
def mock_container():
    settings = SettingsConfig()
    interfaces = InterfacesConfig()
    bus = EventBus()
    container = SystemContainer(settings, interfaces, bus)

    # Мокаем обязательные компоненты
    container.heartbeat = MagicMock()
    container.heartbeat.start = AsyncMock()
    container.heartbeat.stop = MagicMock()

    return container


@pytest.mark.asyncio
@patch("src.system.orchestrator.EventBridge")
async def test_orchestrator_resilience_on_plugin_start_failure(mock_bridge, mock_container):
    """
    Тест: Отказоустойчивость Оркестратора.
    Если один из L2 компонентов (плагинов) падает при вызове .start(),
    Оркестратор должен залогировать ошибку, проигнорировать её и продолжить
    запуск остальных компонентов и Heartbeat'а.
    """
    # Имитируем два плагина (компонента жизненного цикла)
    good_component = MagicMock()
    good_component.start = AsyncMock()

    bad_component = MagicMock()
    bad_component.start = AsyncMock(side_effect=Exception("Критическая ошибка порта!"))

    mock_container.lifecycle_components = [good_component, bad_component]

    orchestrator = SystemOrchestrator(mock_container)

    # Чтобы цикл не завис на ожидании файла agent.stop, мы мокаем этот метод
    orchestrator._watch_for_stop_file = AsyncMock()

    # Запускаем оркестратор
    exit_code = await orchestrator.run()

    # Проверки:
    assert exit_code == 0
    # Здоровый компонент должен был успешно запуститься
    good_component.start.assert_awaited_once()

    # В списке активных компонентов должен остаться только здоровый (чтобы потом корректно вызвался stop)
    assert len(mock_container.lifecycle_components) == 1
    assert mock_container.lifecycle_components[0] == good_component

    # Heartbeat ядра всё равно должен был запуститься
    mock_container.heartbeat.start.assert_awaited_once()


@pytest.mark.asyncio
async def test_orchestrator_stop_gracefully(mock_container):
    """Тест: Оркестратор вызывает stop() у всех активных компонентов."""
    comp1 = MagicMock()
    comp1.stop = AsyncMock()

    comp2 = MagicMock()
    comp2.stop = AsyncMock(side_effect=Exception("Ошибка при остановке"))

    mock_container.lifecycle_components = [comp1, comp2]

    # Мокаем БД
    mock_container.sql = MagicMock()
    mock_container.sql.disconnect = AsyncMock()
    mock_container.vector = MagicMock()
    mock_container.vector.disconnect = AsyncMock()
    mock_container.graph = MagicMock()
    mock_container.graph.disconnect = AsyncMock()
    mock_container.llm_client = MagicMock()
    mock_container.llm_client.close = AsyncMock()

    orchestrator = SystemOrchestrator(mock_container)
    await orchestrator.stop()

    # Убеждаемся, что stop() был вызван (даже если кто-то упал)
    comp1.stop.assert_awaited_once()
    comp2.stop.assert_awaited_once()

    # БД тоже закрыты
    mock_container.sql.disconnect.assert_awaited_once()
    mock_container.vector.disconnect.assert_awaited_once()
    mock_container.graph.disconnect.assert_awaited_once()
