import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.l0_state.agent.state import AgentState
from src.utils.event.bus import EventBus

from src.l2_interfaces.meta.client import MetaClient


@pytest.fixture
def temp_settings_file(tmp_path: Path) -> Path:
    settings_file = tmp_path / "settings.yaml"
    data = """
identity:
  agent_name: AgentEpta
llm:
  model: claude-opus-4.7
  temperature: 0.7
  max_react_steps: 15
system:
  heartbeat_interval: 60
    """
    settings_file.write_text(data.strip(), encoding="utf-8")
    return settings_file


@pytest.fixture
def meta_client(temp_settings_file):    
    """Инициализирует MetaClient с моками шины и стейта."""
    
    agent_state = AgentState()
    bus = MagicMock(spec=EventBus)
    bus.publish = AsyncMock()

    return MetaClient(agent_state=agent_state, event_bus=bus, settings_path=temp_settings_file)