import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

from src.l0_state.interfaces.state import HostTerminalState
from src.utils.settings import HostTerminalConfig
from src.utils.event.bus import EventBus
from src.l2_interfaces.host.terminal.client import HostTerminalClient


@pytest.fixture
def terminal_state():
    return HostTerminalState(context_limit=10)


@pytest.fixture
def terminal_config():
    return HostTerminalConfig(enabled=True, history_limit=50, context_limit=10)


@pytest.fixture
def mock_bus():
    bus = MagicMock(spec=EventBus)
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def terminal_client(terminal_state, terminal_config, tmp_path: Path):
    """Изолированный клиент с временной директорией для сохранения истории."""
    return HostTerminalClient(
        state=terminal_state,
        config=terminal_config,
        data_dir=tmp_path,
        agent_name="TestAgent",
        timezone=3,
    )
