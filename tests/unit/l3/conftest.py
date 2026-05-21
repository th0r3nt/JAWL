import pytest
from unittest.mock import AsyncMock, MagicMock
from src.l0_state.agent.state import AgentState
from src.utils.event.bus import EventBus
from src.l3_agent.llm.executor import LLMExecutor


@pytest.fixture
def mock_executor():
    executor = AsyncMock(spec=LLMExecutor)
    executor.tracker = MagicMock()
    # По дефолту возвращаем empty actions list действий для штатного завершения циклов
    executor.execute.return_value = '{"reflection": "ok", "actions": []}'
    return executor


@pytest.fixture
def mock_dependencies(mock_executor):
    prompt_builder = MagicMock()
    prompt_builder.build.return_value = "System Prompt"

    context_builder = AsyncMock()
    context_builder.build.return_value = "User Context"

    agent_state = AgentState(max_react_steps=3)

    sql_ticks = MagicMock()
    sql_ticks.save_tick = AsyncMock()

    vector_manager = MagicMock()

    tools = [{"type": "function", "function": {"name": "execute_skill"}}]

    return {
        "executor": mock_executor,
        "prompt_builder": prompt_builder,
        "context_builder": context_builder,
        "agent_state": agent_state,
        "sql_ticks": sql_ticks,
        "vector_manager": vector_manager,
        "tools": tools,
        "event_bus": MagicMock(spec=EventBus),
    }
