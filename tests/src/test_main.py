import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from src.main import System, main
from src.utils.event.registry import Events
from src.utils.event.bus import EventBus
from src.utils.settings import load_config


@pytest.fixture
def mock_configs():
    # Загружаем РЕАЛЬНЫЕ дефолтные конфиги
    settings, interfaces = load_config()

    # Отключаем тяжелые/опасные интерфейсы для теста
    interfaces.telegram.telethon.enabled = False
    interfaces.telegram.aiogram.enabled = False
    interfaces.email.enabled = False

    # Ставим безопасные параметры
    interfaces.host.os.access_level = 1

    return settings, interfaces


@pytest.mark.asyncio
async def test_watch_for_stop_file_triggers_shutdown(tmp_path):
    """Тест: файл agent.stop корректно читается и вызывает остановку системы."""
    bus = MagicMock()
    bus.publish = AsyncMock()

    sys_mock = System(
        event_bus=bus, settings_config=MagicMock(), interfaces_config=MagicMock()
    )
    sys_mock.local_data_dir = tmp_path

    stop_file = tmp_path / "agent.stop"

    # Фикс рекурсии: сохраняем оригинальный sleep
    original_sleep = asyncio.sleep

    async def fake_sleep(*args, **kwargs):
        stop_file.touch()
        await original_sleep(0)

    with patch("asyncio.sleep", side_effect=fake_sleep):
        await sys_mock._watch_for_stop_file()

    assert not stop_file.exists()
    bus.publish.assert_called_once_with(
        Events.SYSTEM_SHUTDOWN_REQUESTED, reason="Остановка пользователем из меню"
    )


@patch("src.main.System")
@patch("src.main.load_config")
@patch("src.main.clear_registry")
def test_main_keyboard_interrupt(mock_clear, mock_load, mock_system):
    """Тест: main() ловит KeyboardInterrupt и возвращает код 0 (штатное выключение)."""
    mock_load.return_value = (MagicMock(), MagicMock())

    instance = mock_system.return_value
    instance.run = AsyncMock(side_effect=KeyboardInterrupt())
    instance.stop = AsyncMock()

    exit_code = asyncio.run(main())

    assert exit_code == 0
    instance.stop.assert_awaited_once()


@patch("src.main.System")
@patch("src.main.load_config")
@patch("src.main.clear_registry")
def test_main_critical_exception(mock_clear, mock_load, mock_system):
    """Тест: main() ловит любые исключения и не падает жестко."""
    mock_load.return_value = (MagicMock(), MagicMock())

    instance = mock_system.return_value
    instance.run = AsyncMock(side_effect=RuntimeError("Критический сбой ядра"))
    instance.stop = AsyncMock()

    exit_code = asyncio.run(main())

    assert exit_code == 0
    instance.stop.assert_awaited_once()


@pytest.mark.asyncio
@patch("src.main.SQLManager")
@patch("src.main.VectorManager")
@patch("src.main.Heartbeat")
@patch("src.main.ReactLoop")
async def test_system_di_assembly_smoke(
    mock_react, mock_hb, mock_vector, mock_sql, mock_configs
):
    """Smoke-тест: проверка корректной сборки DI-контейнера."""
    settings, interfaces = mock_configs
    bus = EventBus()

    system = System(event_bus=bus, settings_config=settings, interfaces_config=interfaces)

    # Изолируем БД от диска и делаем методы awaitable
    mock_sql.return_value.connect = AsyncMock()
    mock_sql.return_value.disconnect = AsyncMock()

    mock_vector.return_value.connect = AsyncMock()
    mock_vector.return_value.disconnect = AsyncMock()

    try:
        system.setup_l0_state()
        await system.setup_l1_databases()

        system.setup_l2_interfaces()
        system.setup_l3_agent(llm_api_url="http://test", llm_api_keys=["key1"])

        assert system.agent_state is not None
        assert system.web_search_state is not None
        assert system.llm_client is not None
        assert system.heartbeat is not None

    finally:
        # Теперь stop() успешно выполнит await у моков
        await system.stop()


@pytest.mark.asyncio
async def test_system_shutdown_and_reboot_events(mock_configs):
    """Тест: ядро корректно перехватывает события выключения и перезагрузки."""
    settings, interfaces = mock_configs
    bus = EventBus()

    system = System(event_bus=bus, settings_config=settings, interfaces_config=interfaces)

    # Мокаем Heartbeat, чтобы проверить, что система вызывает его остановку
    system.heartbeat = MagicMock()

    # Активируем подписки
    system._bridge_events_to_heartbeat()

    assert system._exit_code == 0

    # 1. ТЕСТ ПЕРЕЗАГРУЗКИ
    await bus.publish(Events.SYSTEM_REBOOT_REQUESTED)
    if bus.background_tasks:
        await asyncio.gather(*bus.background_tasks)

    assert system._exit_code == 1
    system.heartbeat.stop.assert_called_once()

    system.heartbeat.stop.reset_mock()

    # 2. ТЕСТ ВЫКЛЮЧЕНИЯ
    await bus.publish(Events.SYSTEM_SHUTDOWN_REQUESTED)
    if bus.background_tasks:
        await asyncio.gather(*bus.background_tasks)

    assert system._exit_code == 0
    system.heartbeat.stop.assert_called_once()
