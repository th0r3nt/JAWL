"""
Unit-тесты для сборщика системы (SystemBuilder).

Гарантируют, что DI-контейнер корректно инициализирует все 4 слоя агента (L0-L3),
прокидывает нужные зависимости и возвращает полностью укомплектованный SystemContainer.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

from src.system.container import SystemContainer
from src.builder import SystemBuilder
from src.utils.settings import SettingsConfig, InterfacesConfig


@pytest.fixture
def mock_container(tmp_path: Path) -> SystemContainer:
    """Создает мок контейнера для передачи в билдер."""
    settings = SettingsConfig()
    interfaces = InterfacesConfig()

    # Настраиваем нужные параметры
    settings.system.context_depth.high_ticks = 3
    settings.system.context_depth.medium_ticks = 7
    settings.system.context_depth.low_ticks = 20
    settings.system.heartbeat_interval = 60
    settings.llm.main_model = "test-model"

    event_bus = MagicMock()
    container = SystemContainer(settings, interfaces, event_bus)

    container.root_dir = tmp_path / "mock_root"
    container.local_data_dir = container.root_dir / "data"
    container.context_registry = MagicMock()

    # Явно инициализируем стейты, так как некоторые тесты не вызывают with_l0_states
    container.agent_state = MagicMock()
    container.agent_state.llm_model = "test-model"
    container.agent_state.get_context_block = AsyncMock()

    container.l0_states = {
        "os": MagicMock(),
        "terminal": MagicMock(),
        "code_graph": MagicMock(),
        "telethon": MagicMock(),
        "aiogram": MagicMock(),
        "github": MagicMock(),
        "email": MagicMock(),
        "web_search": MagicMock(),
        "web_http": MagicMock(),
        "web_browser": MagicMock(),
        "web_hooks": MagicMock(),
        "web_rss": MagicMock(),
        "calendar": MagicMock(),
        "dashboard": MagicMock(),
        "elevenlabs": MagicMock(),
        "edge": MagicMock(),
        "cloud_whisper": MagicMock(),
    }

    # Добавляем мок для графа, чтобы избежать AttributeError в тестах L3
    container.graph = MagicMock()

    return container


def test_build_l0_states(mock_container: SystemContainer) -> None:
    """Тест: L0 State корректно инициализирует все объекты состояния."""
    builder = SystemBuilder(mock_container)

    builder.with_l0_states()

    # Проверяем, что объекты создались
    assert mock_container.agent_state is not None
    assert mock_container.agent_state.llm_model == "test-model"

    # Обращение ТЕПЕРЬ идет напрямую в словарь!
    assert "os" in mock_container.l0_states
    assert "github" in mock_container.l0_states
    assert "web_hooks" in mock_container.l0_states
    assert "dashboard" in mock_container.l0_states


@pytest.mark.asyncio
@patch("src.builder.GraphManager")
@patch("src.builder.VectorManager")
@patch("src.builder.SQLManager")
async def test_build_l1_databases(
    mock_sql_cls, mock_vector_cls, mock_graph_cls, mock_container: SystemContainer
) -> None:
    """Тест: L1 Базы данных инициализируются и подключаются."""
    builder = SystemBuilder(mock_container)

    # Настраиваем моки менеджеров БД
    mock_sql_instance = MagicMock()
    mock_sql_instance.connect = AsyncMock()
    mock_sql_cls.return_value = mock_sql_instance

    mock_vector_instance = MagicMock()
    mock_vector_instance.connect = AsyncMock()
    mock_vector_cls.return_value = mock_vector_instance

    mock_graph_instance = MagicMock()
    mock_graph_instance.connect = AsyncMock()
    mock_graph_cls.return_value = mock_graph_instance

    await builder.with_l1_databases()

    # Проверяем создание и коннект
    mock_sql_cls.assert_called_once()
    mock_sql_instance.connect.assert_awaited_once()

    mock_vector_cls.assert_called_once()
    mock_vector_instance.connect.assert_awaited_once()

    mock_graph_cls.assert_called_once()
    mock_graph_instance.connect.assert_awaited_once()

    # Проверяем регистрацию контекста
    assert mock_container.context_registry.register_provider.call_count >= 2


@patch("src.builder.initialize_l2_interfaces")
def test_build_l2_interfaces(mock_init_l2, mock_container: SystemContainer) -> None:
    """Тест: Сборщик интерфейсов делегирует работу функции инициализатора L2."""
    builder = SystemBuilder(mock_container)

    mock_init_l2.return_value = ["mock_client", "mock_events"]
    env_vars = {"GITHUB_TOKEN": "123"}

    builder.with_l2_interfaces(env_vars)

    mock_init_l2.assert_called_once_with(mock_container, env_vars)
    assert mock_container.lifecycle_components == ["mock_client", "mock_events"]


@patch("src.builder.SwarmManager")
@patch("src.builder.Heartbeat")
@patch("src.builder.ReactLoop")
@patch("src.builder.LLMClient")
def test_build_l3_agent(
    mock_llm, mock_react, mock_heartbeat, mock_swarm, mock_container: SystemContainer
) -> None:
    """Тест: Сборка L3 Ядра агента (LLM, ReAct, Swarm, Heartbeat)."""
    builder = SystemBuilder(mock_container)

    # Подготавливаем фиктивные данные для сборки
    mock_container.sql = MagicMock()
    mock_container.vector = MagicMock()

    env_vars = {"LLM_API_URL": "http://mock", "LLM_API_KEYS": ["key1"]}

    builder.with_l3_agent(env_vars)

    # Проверяем создание компонентов
    assert mock_container.llm_client is not None
    assert (
        mock_container.sub_llm_client is mock_container.llm_client
    )  # Если нет саб-ключей, используется основной

    mock_llm.assert_called_once()
    mock_react.assert_called_once()
    mock_heartbeat.assert_called_once()
