import asyncio
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from src.main import System
from src.utils.event.bus import EventBus
from src.utils.event.registry import Events


@pytest.fixture
def mock_configs():
    # Создаем гибкие моки и явно задаем примитивы, чтобы Pydantic не ругался
    settings = MagicMock()

    # LLM
    settings.llm.model_name = "test-model"
    settings.llm.temperature = 0.7
    settings.llm.max_react_steps = 15

    # System
    settings.system.vector_db.embedding_model = "test-model"
    settings.system.vector_db.vector_size = 384
    settings.system.timezone = 3
    settings.system.heartbeat_interval = 30
    settings.system.continuous_cycle = False
    settings.system.max_mental_state_entities = 10

    # Identity
    settings.identity.agent_name = "TestAgent"

    # Interfaces
    interfaces = MagicMock()
    interfaces.host.os.enabled = True
    interfaces.telegram.telethon.enabled = False
    interfaces.telegram.aiogram.enabled = False
    interfaces.web.enabled = True

    return settings, interfaces


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
    mock_sql.return_value.disconnect = AsyncMock()  # <-- ДОБАВИТЬ

    mock_vector.return_value.connect = AsyncMock()
    mock_vector.return_value.disconnect = AsyncMock()  # <-- ДОБАВИТЬ

    try:
        system.setup_l0_state()
        await system.setup_l1_databases()

        # Чтобы не падал Гейткипер в логах (для красоты)
        interfaces.host.os.madness_level = 1

        system.setup_l2_interfaces()
        system.setup_l3_agent(llm_api_url="http://test", llm_api_keys=["key1"])

        assert system.agent_state is not None
        assert system.web_state is not None
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

    # Изначальный код должен быть 0
    assert system._exit_code == 0

    # 1. ТЕСТ ПЕРЕЗАГРУЗКИ
    await bus.publish(Events.SYSTEM_REBOOT_REQUESTED)
    # Ждем, пока EventBus выполнит обработчики в фоне
    if bus.background_tasks:
        await asyncio.gather(*bus.background_tasks)

    assert system._exit_code == 1
    system.heartbeat.stop.assert_called_once()

    # Сбрасываем счетчик вызовов мока
    system.heartbeat.stop.reset_mock()

    # 2. ТЕСТ ВЫКЛЮЧЕНИЯ
    await bus.publish(Events.SYSTEM_SHUTDOWN_REQUESTED)
    if bus.background_tasks:
        await asyncio.gather(*bus.background_tasks)

    assert system._exit_code == 0
    system.heartbeat.stop.assert_called_once()
