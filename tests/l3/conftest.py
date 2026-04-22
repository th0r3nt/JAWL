import pytest
from unittest.mock import AsyncMock, MagicMock
from src.l0_state.agent.state import AgentState


@pytest.fixture
def mock_openai_response():
    def _create(arguments_json: str, finish_reason: str = "tool_calls"):
        response = MagicMock()
        message = MagicMock()

        if finish_reason == "tool_calls":
            tool_call = MagicMock()
            tool_call.id = "call_123"
            tool_call.function.name = "execute_skill"
            tool_call.function.arguments = arguments_json
            message.tool_calls = [tool_call]
        else:
            message.tool_calls = None
            message.content = arguments_json

        response.choices = [MagicMock(message=message)]
        return response

    return _create


@pytest.fixture
def mock_dependencies():
    llm_client = MagicMock()
    llm_client.rotator = MagicMock()

    prompt_builder = MagicMock()
    prompt_builder.build.return_value = "System Prompt"

    context_builder = AsyncMock()
    context_builder.build.return_value = "User Context"

    agent_state = AgentState(max_react_steps=3)

    sql_ticks = MagicMock()
    sql_ticks.save_tick = AsyncMock()

    vector_manager = MagicMock()
    vector_manager.knowledge.clear_session_cache = MagicMock()
    vector_manager.thoughts.clear_session_cache = MagicMock()

    token_tracker = MagicMock()
    tools = [{"type": "function", "function": {"name": "execute_skill"}}]
    cooldown_sec = 0.2

    return {
        "llm_client": llm_client,
        "prompt_builder": prompt_builder,
        "context_builder": context_builder,
        "agent_state": agent_state,
        "sql_ticks": sql_ticks,
        "vector_manager": vector_manager,
        "token_tracker": token_tracker,
        "tools": tools,
        "cooldown_sec": cooldown_sec,
    }
