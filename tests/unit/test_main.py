import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from src.main import main
from src.system.container import SystemContainer
from src.system.orchestrator import SystemOrchestrator
from src.utils.event.registry import Events
from src.utils.event.bus import EventBus
from src.utils.settings import load_config, SettingsConfig, InterfacesConfig


@pytest.fixture
def mock_configs():
    settings, interfaces = load_config()
    interfaces.telegram.telethon.enabled = False
    interfaces.telegram.aiogram.enabled = False
    interfaces.email.enabled = False
    interfaces.host.os.access_level = 1
    return settings, interfaces


@pytest.mark.asyncio
async def test_watch_for_stop_file_triggers_shutdown(tmp_path):
    """Тест: файл agent.stop корректно читается и вызывает остановку системы."""
    bus = MagicMock()
    bus.publish = AsyncMock()

    container = SystemContainer(
        settings=MagicMock(), interfaces_config=MagicMock(), event_bus=bus
    )
    container.local_data_dir = tmp_path

    orchestrator = SystemOrchestrator(container)
    stop_file = tmp_path / "agent.stop"

    original_sleep = asyncio.sleep

    async def fake_sleep(*args, **kwargs):
        stop_file.touch()
        await original_sleep(0)

    with patch("asyncio.sleep", side_effect=fake_sleep):
        await orchestrator._watch_for_stop_file()

    assert not stop_file.exists()
    bus.publish.assert_called_once_with(
        Events.SYSTEM_SHUTDOWN_REQUESTED, reason="Остановка пользователем из меню"
    )
@patch("src.main.SystemOrchestrator")
@patch("src.main.SystemBuilder")
@patch("src.main.load_config")
@patch("src.main.clear_registry")
def test_main_keyboard_interrupt(mock_clear, mock_load, mock_builder_cls, mock_orchestrator):
    """Тест: main() ловит KeyboardInterrupt и возвращает код 0."""
    mock_load.return_value = (SettingsConfig(), InterfacesConfig())

    # Мокаем Builder, чтобы не поднимались реальные БД
    mock_builder_instance = MagicMock()
    mock_builder_instance.with_l1_databases = AsyncMock()
    mock_builder_cls.return_value = mock_builder_instance

    instance = mock_orchestrator.return_value
    instance.run = AsyncMock(side_effect=KeyboardInterrupt())
    instance.stop = AsyncMock()

    exit_code = asyncio.run(main())

    assert exit_code == 0
    instance.stop.assert_awaited_once()


@patch("src.main.SystemOrchestrator")
@patch("src.main.SystemBuilder")
@patch("src.main.load_config")
@patch("src.main.clear_registry")
def test_main_critical_exception(mock_clear, mock_load, mock_builder_cls, mock_orchestrator):
    """Тест: main() ловит любые исключения и не падает жестко."""
    mock_load.return_value = (SettingsConfig(), InterfacesConfig())

    # Мокаем Builder, чтобы не поднимались реальные БД
    mock_builder_instance = MagicMock()
    mock_builder_instance.with_l1_databases = AsyncMock()
    mock_builder_cls.return_value = mock_builder_instance

    instance = mock_orchestrator.return_value
    instance.run = AsyncMock(side_effect=RuntimeError("Критический сбой ядра"))
    instance.stop = AsyncMock()

    exit_code = asyncio.run(main())

    assert exit_code == 0
    instance.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_system_shutdown_and_reboot_events(mock_configs):
    """Тест: ядро корректно перехватывает события выключения и перезагрузки."""
    settings, interfaces = mock_configs
    bus = EventBus()

    container = SystemContainer(settings, interfaces, bus)
    container.heartbeat = MagicMock()

    orchestrator = SystemOrchestrator(container)  # noqa: F841

    from src.utils.event.bridge import EventBridge

    EventBridge(container).setup_routing()

    assert container.exit_code == 0

    await bus.publish(Events.SYSTEM_REBOOT_REQUESTED)
    if bus.background_tasks:
        await asyncio.gather(*bus.background_tasks)

    assert container.exit_code == 1
    container.heartbeat.stop.assert_called_once()

    container.heartbeat.stop.reset_mock()

    await bus.publish(Events.SYSTEM_SHUTDOWN_REQUESTED)
    if bus.background_tasks:
        await asyncio.gather(*bus.background_tasks)

    assert container.exit_code == 0
    container.heartbeat.stop.assert_called_once()


@pytest.mark.asyncio
async def test_system_stop_closes_all_llm_clients(mock_configs):
    """Тест: При остановке закрываются обе сессии, если они разные."""
    settings, interfaces = mock_configs
    bus = EventBus()

    container = SystemContainer(settings, interfaces, bus)

    mock_main_llm = AsyncMock()
    mock_sub_llm = AsyncMock()

    container.llm_client = mock_main_llm
    container.sub_llm_client = mock_sub_llm

    orchestrator = SystemOrchestrator(container)
    await orchestrator.stop()

    mock_main_llm.close.assert_awaited_once()
    mock_sub_llm.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_system_stop_shared_llm_client_closes_once(mock_configs):
    """Тест: При остановке общий клиент закрывается только один раз."""
    settings, interfaces = mock_configs
    bus = EventBus()

    container = SystemContainer(settings, interfaces, bus)
    mock_llm = AsyncMock()

    container.llm_client = mock_llm
    container.sub_llm_client = mock_llm

    orchestrator = SystemOrchestrator(container)
    await orchestrator.stop()

    mock_llm.close.assert_awaited_once()
