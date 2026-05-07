import pytest
from unittest.mock import MagicMock, AsyncMock

from src.utils.settings import (
    SubconsciousConfig,
    SubconsciousPatternsConfig,
    SubconsciousPatternConfig,
)
from src.l0_state.agent.state import AgentState
from src.utils.event.bus import EventBus
from src.utils.token_tracker import TokenTracker


@pytest.fixture
def mock_subconscious_config():
    return SubconsciousConfig(
        enabled=True,
        llm_model="cheap-model",
        patterns=SubconsciousPatternsConfig(
            consolidation=SubconsciousPatternConfig(enabled=True, activation_limit_ticks=2),
            reflection=SubconsciousPatternConfig(enabled=True, activation_limit_ticks=3),
            forgetting=SubconsciousPatternConfig(enabled=False, activation_limit_ticks=10),
        ),
    )


@pytest.fixture
def mock_subconscious_deps(mock_subconscious_config, tmp_path):
    bus = MagicMock(spec=EventBus)
    bus.publish = AsyncMock()

    agent_state = AgentState()

    sql = MagicMock()
    vector = MagicMock()
    graph = MagicMock()
    llm = MagicMock()
    tracker = MagicMock(spec=TokenTracker)

    return {
        "config": mock_subconscious_config,
        "llm_client": llm,
        "sql_manager": sql,
        "vector_manager": vector,
        "graph_manager": graph,
        "sql_ticks": MagicMock(),
        "token_tracker": tracker,
        "event_bus": bus,
        "agent_state": agent_state,
        "root_dir": tmp_path,
    }
