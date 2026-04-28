import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.l0_state.agent.state import AgentState
from src.utils.event.bus import EventBus
from src.l2_interfaces.meta.client import MetaClient


@pytest.fixture
def tmp_settings(tmp_path: Path) -> Path:
    p = tmp_path / "settings.yaml"
    data = """
llm:
  model: "claude-opus-4.7"
  available_models:
    - "claude-opus-4.7"
    - "gpt-4o"
  temperature: 0.7
  max_react_steps: 15
system:
  heartbeat_interval: 60
  sql:
    tasks:
      max_tasks: 10
    mental_states:
      max_entities: 5
  context_depth:
    ticks: 15
    detailed_ticks: 3
"""
    p.write_text(data.strip(), encoding="utf-8")
    return p


@pytest.fixture
def tmp_interfaces(tmp_path: Path) -> Path:
    p = tmp_path / "interfaces.yaml"
    data = """
host:
  os:
    enabled: false
telegram:
  telethon:
    enabled: true
"""
    p.write_text(data.strip(), encoding="utf-8")
    return p


@pytest.fixture
def meta_client(tmp_settings, tmp_interfaces):
    agent_state = AgentState(llm_model="claude-opus-4.7", temperature=0.7)
    bus = MagicMock(spec=EventBus)
    bus.publish = AsyncMock()

    return MetaClient(
        agent_state=agent_state,
        event_bus=bus,
        settings_path=tmp_settings,
        interfaces_path=tmp_interfaces,
        access_level=2,
        available_models=["claude-opus-4.7", "gpt-4o"],
        custom_skills_enabled=True,
    )