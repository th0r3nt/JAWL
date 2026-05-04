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
@patch("src.builder.GraphManager")
@patch("src.builder.SQLManager")
@patch("src.builder.VectorManager")
@patch("src.builder.Heartbeat")
@patch("src.builder.ReactLoop")
async def test_system_di_assembly_smoke(
    mock_react, mock_hb, mock_vector, mock_sql, mock_graph, mock_configs
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

    mock_graph.return_value.connect = AsyncMock()
    mock_graph.return_value.disconnect = AsyncMock()

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
        await system.stop()


@pytest.mark.asyncio
async def test_system_shutdown_and_reboot_events(mock_configs):
    """Тест: ядро корректно перехватывает события выключения и перезагрузки."""
    settings, interfaces = mock_configs
    bus = EventBus()

    system = System(event_bus=bus, settings_config=settings, interfaces_config=interfaces)
    system.heartbeat = MagicMock()
    system._bridge_events_to_heartbeat()

    assert system._exit_code == 0

    await bus.publish(Events.SYSTEM_REBOOT_REQUESTED)
    if bus.background_tasks:
        await asyncio.gather(*bus.background_tasks)

    assert system._exit_code == 1
    system.heartbeat.stop.assert_called_once()

    system.heartbeat.stop.reset_mock()

    await bus.publish(Events.SYSTEM_SHUTDOWN_REQUESTED)
    if bus.background_tasks:
        await asyncio.gather(*bus.background_tasks)

    assert system._exit_code == 0
    system.heartbeat.stop.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.asyncio
@patch("src.builder.GraphManager")
@patch("src.builder.SQLManager")
@patch("src.builder.VectorManager")
@patch("src.builder.Heartbeat")
@patch("src.builder.ReactLoop")
async def test_system_subagent_llm_fallback(
    mock_react, mock_hb, mock_vector, mock_sql, mock_graph, mock_configs
):
    """Тест: Если SUB_ ключи не переданы, субагенты используют основной LLM клиент."""
    settings, interfaces = mock_configs
    bus = EventBus()
    system = System(event_bus=bus, settings_config=settings, interfaces_config=interfaces)

    system.setup_l0_state()
    system.sys_cfg = settings.system

    system.sql = mock_sql.return_value
    system.vector = mock_vector.return_value
    system.graph = mock_graph.return_value

    system.setup_l3_agent(llm_api_url="http://main", llm_api_keys=["main_key"])

    assert system.sub_llm_client is system.llm_client
    assert system.sub_llm_client.api_url == "http://main"


@pytest.mark.asyncio
@patch("src.builder.GraphManager")
@patch("src.builder.SQLManager")
@patch("src.builder.VectorManager")
@patch("src.builder.Heartbeat")
@patch("src.builder.ReactLoop")
async def test_system_subagent_dedicated_llm(
    mock_react, mock_hb, mock_vector, mock_sql, mock_graph, mock_configs
):
    """Тест: Если SUB_ ключи переданы, создаются два независимых клиента."""
    settings, interfaces = mock_configs
    bus = EventBus()
    system = System(event_bus=bus, settings_config=settings, interfaces_config=interfaces)

    system.setup_l0_state()
    system.sys_cfg = settings.system

    system.sql = mock_sql.return_value
    system.vector = mock_vector.return_value
    system.graph = mock_graph.return_value

    system.setup_l3_agent(
        llm_api_url="http://main",
        llm_api_keys=["main_key"],
        sub_llm_api_url="http://sub",
        sub_llm_api_keys=["sub_key_1", "sub_key_2"],
    )

    assert system.sub_llm_client is not system.llm_client
    assert system.sub_llm_client.api_url == "http://sub"
    assert system.sub_llm_client.rotator.keys == ["sub_key_1", "sub_key_2"]


@pytest.mark.asyncio
async def test_system_stop_closes_all_llm_clients(mock_configs):
    """Тест: При остановке закрываются обе сессии, если они разные."""
    settings, interfaces = mock_configs
    bus = EventBus()
    system = System(event_bus=bus, settings_config=settings, interfaces_config=interfaces)

    mock_main_llm = AsyncMock()
    mock_sub_llm = AsyncMock()

    system.llm_client = mock_main_llm
    system.sub_llm_client = mock_sub_llm

    await system.stop()

    mock_main_llm.close.assert_awaited_once()
    mock_sub_llm.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_system_stop_shared_llm_client_closes_once(mock_configs):
    """Тест: При остановке общий клиент закрывается только один раз."""
    settings, interfaces = mock_configs
    bus = EventBus()
    system = System(event_bus=bus, settings_config=settings, interfaces_config=interfaces)

    mock_llm = AsyncMock()

    system.llm_client = mock_llm
    system.sub_llm_client = mock_llm

    await system.stop()
    mock_llm.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_system_di_assembly_avoids_db_file_locks(mock_configs, tmp_path):
    """
    Регрессионный тест: гарантия того, что DI-сборщик в тестовом режиме
    не касается реальных баз данных. Защищает pytest от SQLite/KuzuDB File Locks,
    позволяя агенту запускать pytest из песочницы "на горячую".
    """
    settings, interfaces = mock_configs

    with patch("src.builder.GraphManager") as mock_graph_internal, patch(
        "src.builder.SQLManager"
    ) as mock_sql_internal, patch("src.builder.VectorManager") as mock_vector_internal:

        mock_graph_internal.return_value.connect = AsyncMock()
        mock_sql_internal.return_value.connect = AsyncMock()
        mock_vector_internal.return_value.connect = AsyncMock()

        from src.builder import SystemBuilder
        from src.main import System

        sys = System(
            event_bus=MagicMock(), settings_config=settings, interfaces_config=interfaces
        )
        sys.root_dir = tmp_path / "mock_root"
        sys.local_data_dir = sys.root_dir / "data"

        builder = SystemBuilder(sys)

        builder.build_l0_state()
        await builder.build_l1_databases()

        mock_graph_internal.assert_called_once()
        mock_sql_internal.assert_called_once()
        mock_vector_internal.assert_called_once()
