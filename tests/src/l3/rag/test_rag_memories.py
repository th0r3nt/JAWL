import pytest
from unittest.mock import AsyncMock, MagicMock
from src.utils.settings import RAGConfig
from src.l3_agent.context.rag.memories import RAGMemories
from src.l3_agent.skills.registry import SkillResult
from src.l0_state.agent.state import AgentState


@pytest.mark.asyncio
async def test_rag_memories_context_extraction():
    """Тест: RAG корректно извлекает контекст из векторных заглушек."""
    mock_knowledge = AsyncMock()
    mock_thoughts = AsyncMock()

    mock_knowledge.search_knowledge.return_value = SkillResult.ok(
        "[ID: `111`] Факт: Сервер находится в шкафу."
    )
    mock_thoughts.search_thoughts.return_value = SkillResult.ok(
        "[ID: `222`] Мысль: Шкаф надо проветривать."
    )

    mock_telethon_state = MagicMock()
    mock_telethon_state.last_chats = "User | ID: 123 | Название: John_Admin[UNREAD: 1]"

    mock_agent_state = AgentState()
    rag_config = RAGConfig(
        enabled=True,
        depth_limit=1,
        max_vector_blocks=5,
        max_graph_nodes=5,
        max_query_chars=200,
    )

    # Подменяем внутренние компоненты оркестратора для юнита
    mock_orchestrator = AsyncMock()
    mock_orchestrator.run.return_value = (
        "RELEVANT INFORMATION\nФакт: Сервер находится в шкафу.\nМысль: Шкаф надо проветривать."
    )

    rag = RAGMemories(
        vector_knowledge=mock_knowledge,
        vector_thoughts=mock_thoughts,
        graph_manager=None,
        embedding_model=MagicMock(),
        telethon_state=mock_telethon_state,
        agent_state=mock_agent_state,
        rag_config=rag_config,
    )
    rag.orchestrator = mock_orchestrator

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
    mock_orchestrator.run.assert_called_once()


@pytest.mark.asyncio
async def test_rag_memories_uses_raw_text():
    """Тест: RAG отдает приоритет raw_text для очистки от медиа-тегов."""
    mock_knowledge = AsyncMock()
    mock_thoughts = AsyncMock()
    mock_telethon_state = MagicMock()
    mock_telethon_state.last_chats = ""
    mock_agent_state = AgentState()

    rag_config = RAGConfig()

    mock_orchestrator = AsyncMock()
    mock_orchestrator.run.return_value = ""

    rag = RAGMemories(
        vector_knowledge=mock_knowledge,
        vector_thoughts=mock_thoughts,
        graph_manager=None,
        embedding_model=MagicMock(),
        telethon_state=mock_telethon_state,
        agent_state=mock_agent_state,
        rag_config=rag_config,
    )
    rag.orchestrator = mock_orchestrator

    payload = {
        "sender_name": "Alice",
        "message": "[Фотография][Переслано от: Бот] Вот сам текст",
        "raw_text": "Вот сам текст",
    }

    await rag.get_context_block(payload=payload, missed_events=[])

    # Проверяем, что в оркестратор ушел именно чистый текст
    called_texts = mock_orchestrator.run.call_args[0][0]
    assert "Вот сам текст" in called_texts
    assert "[Фотография][Переслано от: Бот] Вот сам текст" not in called_texts


# ===================================================================
# ТЕСТЫ: АЛГОРИТМ ЧАНКИНГА И РЕЗОЛВИНГА (EntityExtractor)
# ===================================================================


def test_rag_entity_extractor_chunking():
    """Тест: механизм семантического разбиения текста (Chunking) для Embedding моделей."""
    from src.l3_agent.context.rag.entity_extractor import EntityExtractor

    extractor = EntityExtractor(max_query_chars=50)

    # 1. Текст меньше лимита не разбивается
    short_text = "Короткий запрос."
    chunks = extractor.extract_vector_queries(short_text)
    assert len(chunks) == 1
    assert chunks[0] == short_text

    # 2. Текст аккуратно режется по предложениям
    medium_text = "Это первое предложение. Это второе предложение! А вот это уже третье."
    chunks = extractor.extract_vector_queries(medium_text)
    assert len(chunks) == 2
    assert "первое" in chunks[0]
    assert "второе" in chunks[0]
    assert "третье" in chunks[1]

    # 3. Жесткая обрезка "Монолитного" предложения (без точек), превышающего лимит
    long_monolith = "Это гигантское предложение без знаков препинания которое должно быть жестко обрезано посимвольно."
    chunks = extractor.extract_vector_queries(long_monolith)

    assert len(chunks) > 1
    assert len(chunks[0]) <= 50
    assert chunks[0].startswith("Это гигантское предложение")


def test_rag_entity_extractor_rapidfuzz():
    """Тест: механизм RapidFuzz корректно извлекает сущности с учетом падежей (русский язык)."""
    from src.l3_agent.context.rag.entity_extractor import EntityExtractor

    extractor = EntityExtractor(engine="rapidfuzz")

    # Имитируем узлы в графе (в именительном падеже)
    vocab = ["Стив Джобс", "Apple", "API", "ИИ"]
    extractor.build_graph_vocabulary(vocab)

    # Текст с падежами и склонениями
    text = "Агент, расскажи про Стива Джобса и какое-то Яблоко? И проверь API для ИИ."

    found_nodes = extractor.extract_graph_nodes(text)

    # RapidFuzz должен понять, что "Стива Джобса" это "Стив Джобс" (fuzzy match > 80.0)
    assert "Стив Джобс" in found_nodes

    # Короткие слова (API, ИИ) ищутся по exact match с границами слов, чтобы избежать ложных срабатываний
    assert "API" in found_nodes
    assert "ИИ" in found_nodes

    # "Apple" в тексте не было, было только русское "Яблоко", так что не должен найти
    assert "Apple" not in found_nodes