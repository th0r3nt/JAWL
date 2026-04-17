import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from src.main import System
from src.utils.event.bus import EventBus


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
    settings.system.loop_interval_sec = 30
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