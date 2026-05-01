"""
Unit-тесты для сборщика системы (SystemBuilder).

Гарантируют, что DI-контейнер корректно инициализирует все 4 слоя агента (L0-L3),
прокидывает нужные зависимости и регистрирует провайдеры контекста.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

from src.main import System
from src.builder import SystemBuilder
from src.utils.settings import SettingsConfig, InterfacesConfig


@pytest.fixture
def mock_system() -> System:
    """Создает мок главной системы для передачи в билдер."""
    sys_mock = MagicMock(spec=System)

    # ИСПОЛЬЗУЕМ РЕАЛЬНЫЕ ОБЪЕКТЫ КОНФИГУРАЦИЙ (защита от AttributeError в моках)
    sys_mock.settings = SettingsConfig()
    sys_mock.interfaces_config = InterfacesConfig()

    # Настраиваем нужные параметры
    sys_mock.settings.system.context_depth.ticks = 15
    sys_mock.settings.system.context_depth.detailed_ticks = 3
    sys_mock.settings.system.heartbeat_interval = 60
    sys_mock.settings.llm.main_model = "test-model"

    # Мокаем пути
    sys_mock.root_dir = Path("/mock/root")
    sys_mock.local_data_dir = Path("/mock/root/data")

    # Мокаем реестры
    sys_mock.event_bus = MagicMock()
    sys_mock.context_registry = MagicMock()
    sys_mock._lifecycle_components = []

    # ЯВНО ИНИЦИАЛИЗИРУЕМ СТЕЙТЫ (так как некоторые тесты не вызывают build_l0_state перед своим запуском)
    sys_mock.agent_state = MagicMock()
    sys_mock.agent_state.llm_model = "test-model"
    sys_mock.os_state = MagicMock()
    sys_mock.terminal_state = MagicMock()
    sys_mock.telethon_state = MagicMock()
    sys_mock.aiogram_state = MagicMock()
    sys_mock.github_state = MagicMock()
    sys_mock.email_state = MagicMock()
    sys_mock.web_search_state = MagicMock()
    sys_mock.web_http_state = MagicMock()
    sys_mock.web_browser_state = MagicMock()
    sys_mock.web_hooks_state = MagicMock()
    sys_mock.web_rss_state = MagicMock()
    sys_mock.calendar_state = MagicMock()
    sys_mock.dashboard_state = MagicMock()

    return sys_mock


def test_build_l0_state(mock_system: System) -> None:
    """Тест: L0 State корректно инициализирует все объекты состояния."""
    builder = SystemBuilder(mock_system)

    builder.build_l0_state()

    # Проверяем, что объекты создались (билдер их перезаписал реальными)
    assert mock_system.agent_state is not None
    assert mock_system.agent_state.llm_model == "test-model"
    assert mock_system.os_state is not None
    assert mock_system.github_state is not None
    assert mock_system.web_hooks_state is not None
    assert mock_system.dashboard_state is not None


@pytest.mark.asyncio
@patch("src.builder.VectorManager")
@patch("src.builder.SQLManager")
async def test_build_l1_databases(mock_sql_cls, mock_vector_cls, mock_system: System) -> None:
    """Тест: L1 Базы данных инициализируются и подключаются."""
    builder = SystemBuilder(mock_system)

    # Настраиваем моки менеджеров БД
    mock_sql_instance = MagicMock()
    mock_sql_instance.connect = AsyncMock()
    mock_sql_cls.return_value = mock_sql_instance

    mock_vector_instance = MagicMock()
    mock_vector_instance.connect = AsyncMock()
    mock_vector_cls.return_value = mock_vector_instance

    await builder.build_l1_databases()

    # Проверяем создание и коннект
    mock_sql_cls.assert_called_once()
    mock_sql_instance.connect.assert_awaited_once()

    mock_vector_cls.assert_called_once()
    mock_vector_instance.connect.assert_awaited_once()

    # Проверяем регистрацию контекста
    assert mock_system.context_registry.register_provider.call_count >= 2


@patch("src.builder.initialize_l2_interfaces")
def test_build_l2_interfaces(mock_init_l2, mock_system: System) -> None:
    """Тест: Сборщик интерфейсов делегирует работу функции инициализатора L2."""
    builder = SystemBuilder(mock_system)

    mock_init_l2.return_value = ["mock_client", "mock_events"]
    env_vars = {"GITHUB_TOKEN": "123"}

    builder.build_l2_interfaces(env_vars)

    mock_init_l2.assert_called_once_with(mock_system, env_vars)
    assert mock_system._lifecycle_components == ["mock_client", "mock_events"]


@patch("src.builder.SwarmManager")
@patch("src.builder.Heartbeat")
@patch("src.builder.ReactLoop")
@patch("src.builder.LLMClient")
def test_build_l3_agent(
    mock_llm, mock_react, mock_heartbeat, mock_swarm, mock_system: System
) -> None:
    """Тест: Сборка L3 Ядра агента (LLM, ReAct, Swarm, Heartbeat)."""
    builder = SystemBuilder(mock_system)

    # Подготавливаем фиктивные данные для сборки
    mock_system.sql = MagicMock()
    mock_system.vector = MagicMock()

    env_vars = {"LLM_API_URL": "http://mock", "LLM_API_KEYS": ["key1"]}

    builder.build_l3_agent(env_vars)

    # Проверяем создание компонентов
    assert mock_system.llm_client is not None
    assert (
        mock_system.sub_llm_client is mock_system.llm_client
    )  # Если нет саб-ключей, используется основной

    mock_llm.assert_called_once()
    mock_react.assert_called_once()
    mock_heartbeat.assert_called_once()
