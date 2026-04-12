import pytest
from unittest.mock import AsyncMock, MagicMock

from src.l3_agent.context.builder import ContextBuilder
from src.l0_state.interfaces.state import (
    HostOSState,
    TelethonState,
    AiogramState,
    HostTerminalState,
    WebState,
)
from src.l0_state.agent.state import AgentState
from src.l3_agent.skills.registry import SkillResult
from src.utils.settings import ContextDepthConfig


@pytest.fixture
def mock_states():
    os_state = HostOSState()
    os_state.is_online = True
    os_state.datetime = "2026-01-01 12:00:00"
    os_state.uptime = "2 days"
    os_state.telemetry = "CPU: 15%"

    telethon_state = TelethonState()
    telethon_state.is_online = True
    telethon_state.last_chats = "Telethon: User 1"

    aiogram_state = AiogramState()
    aiogram_state.is_online = True
    aiogram_state.last_chats = "Aiogram: User 2"

    terminal_state = HostTerminalState()
    terminal_state.is_online = True
    terminal_state.is_ui_connected = True
    terminal_state.messages = "Admin: Wake up"

    agent_state = AgentState()
    agent_state.llm_model = "test-model"

    return os_state, telethon_state, aiogram_state, terminal_state, agent_state


@pytest.fixture
def mock_dbs():
    sql_ticks = MagicMock()
    # Имитируем один старый тик
    mock_tick = MagicMock()
    mock_tick.thoughts = "I think, therefore I am."
    mock_tick.actions = [{"tool_name": "test_func", "parameters": {}}]
    mock_tick.results = {"test_func": "ok"}
    sql_ticks.get_ticks = AsyncMock(return_value=[mock_tick])

    sql_tasks = MagicMock()
    sql_tasks.get_tasks = AsyncMock(return_value=SkillResult.ok("Task: Fix bugs"))

    sql_traits = MagicMock()
    sql_traits.get_traits = AsyncMock(return_value=SkillResult.ok("Trait: Sarcasm"))

    return sql_ticks, sql_tasks, sql_traits


@pytest.mark.asyncio
async def test_context_builder_build(mock_states, mock_dbs):
    os_state, telethon_state, aiogram_state, terminal_state, agent_state = mock_states
    sql_ticks, sql_tasks, sql_traits = mock_dbs

    depth_config = ContextDepthConfig(ticks=5)
    interfaces_config = MagicMock()
    vector_db_config = MagicMock()

    builder = ContextBuilder(
        host_os_state=os_state,
        telethon_state=telethon_state,
        aiogram_state=aiogram_state,
        terminal_state=terminal_state,
        web_state=WebState(),
        agent_state=agent_state,
        sql_ticks=sql_ticks,
        sql_tasks=sql_tasks,
        sql_traits=sql_traits,
        vector_knowledge=MagicMock(),
        vector_thoughts=MagicMock(),
        vector_db_config=vector_db_config,
        depth_config=depth_config,
        interfaces_config=interfaces_config,
        timezone=3,
    )

    payload = {"chat_id": 123, "text": "Hello Agent"}
    context = await builder.build(event_name="TEST_EVENT", payload=payload, missed_events=[])

    assert "## PERSONALITY TRAITS" in context
    assert "Trait: Sarcasm" in context
    assert "## TASKS" in context
    assert "Task: Fix bugs" in context
    assert "## STATE" in context
    assert "test-model" in context
    assert "Telethon: User 1" in context
    assert "Aiogram: User 2" in context
    assert "## RECENT TICKS" in context
    assert "I think, therefore I am." in context
    assert "`test_func`({})" in context
    assert "## WAKE UP REASON" in context
    assert "TEST_EVENT" in context
    assert "chat_id: 123" in context
    assert "text: Hello Agent" in context


@pytest.mark.asyncio
async def test_build_rag_memories_regex(mock_states, mock_dbs):
    """Тест: защита RAG-парсера от мусорных строк и регулярных сбоев."""
    os_state, telethon_state, aiogram_state, terminal_state, agent_state = mock_states
    sql_ticks, sql_tasks, sql_traits = mock_dbs

    vector_knowledge = MagicMock()
    vector_knowledge.search_knowledge = AsyncMock(return_value=SkillResult.ok("Fact"))
    vector_thoughts = MagicMock()
    vector_thoughts.search_thoughts = AsyncMock(return_value=SkillResult.ok("Thought"))

    builder = ContextBuilder(
        host_os_state=os_state,
        telethon_state=telethon_state,
        aiogram_state=aiogram_state,
        terminal_state=terminal_state,
        web_state=MagicMock(),
        agent_state=agent_state,
        sql_ticks=sql_ticks,
        sql_tasks=sql_tasks,
        sql_traits=sql_traits,
        vector_knowledge=vector_knowledge,
        vector_thoughts=vector_thoughts,
        vector_db_config=MagicMock(auto_rag_top_k=2),
        depth_config=ContextDepthConfig(),
        interfaces_config=MagicMock(),
        timezone=3,
    )

    # Мусорные данные с переносами строк и спецсимволами
    payload = {"sender_name": "Ugly \n Name", "message": "Short"}
    missed_events = [
        "Event | Payload: sender_name=Valid User, message=Valid long message for regex test",
        "Event | Payload: sender_name=Unknown, message=A",  # Слишком короткое
        "Broken string without payload format",
    ]

    rag_context = await builder._build_rag_memories(payload, missed_events)

    # Проверяем, что поиск не упал, а валидные запросы были отправлены
    assert "Valid long message for regex test" in rag_context
    assert "Valid User" in rag_context
    assert "Ugly \n Name" in rag_context
