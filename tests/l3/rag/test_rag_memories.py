import pytest
from unittest.mock import AsyncMock, MagicMock
from src.l3_agent.context.rag.memories import RAGMemories
from src.l3_agent.skills.registry import SkillResult
from src.l0_state.agent.state import AgentState
from src.utils.event.registry import Events


@pytest.mark.asyncio
async def test_rag_memories_context_extraction():
    # Мокаем БД
    mock_knowledge = AsyncMock()
    mock_thoughts = AsyncMock()

    mock_knowledge.search_knowledge.return_value = SkillResult.ok(
        "[ID: `111`] Факт: Сервер находится в шкафу."
    )

    mock_thoughts.search_thoughts.return_value = SkillResult.ok(
        "[ID: `222`] Мысль: Шкаф надо проветривать."
    )

    mock_telegram_user_state = MagicMock()
    mock_telegram_user_state.last_chats = "User | ID: 123 | Название: John_Admin [UNREAD: 1]"

    # Имитируем стейт агента
    mock_agent_state = AgentState()

    rag = RAGMemories(
        mock_knowledge,
        mock_thoughts,
        telegram_user_state=mock_telegram_user_state,
        agent_state=mock_agent_state,
        auto_rag_top_k=2,
    )

    payload = {"sender_name": "Alice", "message": "Где сервер?"}

    missed_events = [
        {
            "name": Events.KURIGRAM_MESSAGE_INCOMING.name,
            "level": "HIGH",
            "payload": {"sender_name": "Bob", "message": "Срочно нужна помощь!"},
        }
    ]

    context = await rag.get_context_block(payload=payload, missed_events=missed_events)

    assert "RELEVANT INFORMATION" in context
    assert "Сервер находится в шкафу" in context
    assert "Шкаф надо проветривать" in context

    assert mock_knowledge.search_knowledge.call_count >= 3


def test_rag_memories_accepts_legacy_telethon_state_keyword():
    rag = RAGMemories(
        AsyncMock(),
        AsyncMock(),
        telethon_state=MagicMock(last_chats=""),
        agent_state=AgentState(),
    )

    assert rag.telethon_state is rag.telegram_user_state
