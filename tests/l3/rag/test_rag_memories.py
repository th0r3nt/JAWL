import pytest
from unittest.mock import AsyncMock, MagicMock
from src.l3_agent.context.rag.memories import RAGMemories
from src.l3_agent.skills.registry import SkillResult
from src.l0_state.agent.state import AgentState


@pytest.mark.asyncio
async def test_rag_memories_context_extraction():
    mock_knowledge = AsyncMock()
    mock_thoughts = AsyncMock()

    mock_knowledge.search_knowledge.return_value = SkillResult.ok(
        "[ID: `111`] Факт: Сервер находится в шкафу."
    )
    mock_thoughts.search_thoughts.return_value = SkillResult.ok(
        "[ID: `222`] Мысль: Шкаф надо проветривать."
    )

    mock_telethon_state = MagicMock()
    mock_telethon_state.last_chats = "User | ID: 123 | Название: John_Admin [UNREAD: 1]"

    mock_agent_state = AgentState()

    rag = RAGMemories(
        mock_knowledge,
        mock_thoughts,
        mock_telethon_state,
        agent_state=mock_agent_state,
        auto_rag_top_k=2,
    )

    payload = {"sender_name": "Alice", "message": "Где сервер?", "raw_text": "Где сервер?"}

    missed_events = [
        {
            "name": "TELETHON_MESSAGE_INCOMING",
            "level": "HIGH",
            "payload": {
                "sender_name": "Bob",
                "message": "Срочно нужна помощь!",
                "raw_text": "Срочно нужна помощь!",
            },
        }
    ]

    context = await rag.get_context_block(payload=payload, missed_events=missed_events)

    assert "RELEVANT INFORMATION" in context
    assert "Сервер находится в шкафу" in context
    assert "Шкаф надо проветривать" in context

    assert mock_knowledge.search_knowledge.call_count >= 3


@pytest.mark.asyncio
async def test_rag_memories_uses_raw_text():
    """Тест: RAG отдает приоритет raw_text для очистки от медиа-тегов."""
    mock_knowledge = AsyncMock()
    mock_thoughts = AsyncMock()

    mock_knowledge.search_knowledge.return_value = SkillResult.ok("")
    mock_thoughts.search_thoughts.return_value = SkillResult.ok("")

    mock_telethon_state = MagicMock()
    mock_telethon_state.last_chats = ""
    mock_agent_state = AgentState()

    rag = RAGMemories(
        mock_knowledge, mock_thoughts, mock_telethon_state, mock_agent_state, auto_rag_top_k=1
    )

    payload = {
        "sender_name": "Alice",
        "message": "[Фотография] [Переслано от: Бот] Вот сам текст",
        "raw_text": "Вот сам текст",
    }

    await rag.get_context_block(payload=payload, missed_events=[])

    calls = mock_knowledge.search_knowledge.call_args_list
    queried_texts = [call[1]["query"] for call in calls]

    assert "Вот сам текст" in queried_texts
    assert "[Фотография] [Переслано от: Бот] Вот сам текст" not in queried_texts
