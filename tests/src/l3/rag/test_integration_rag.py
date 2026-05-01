import pytest
from pathlib import Path
from unittest.mock import MagicMock

from src.l0_state.agent.state import AgentState
from src.l1_databases.vector.db import VectorDB
from src.l1_databases.vector.collections import VectorCollection
from src.l1_databases.vector.management.knowledge import VectorKnowledge
from src.l1_databases.vector.management.thoughts import VectorThoughts
from src.l3_agent.context.rag.memories import RAGMemories

# Импортируем мок-модель эмбеддингов, созданную нами ранее для юнит тестов Векторной БД
from tests.src.l1.vector.conftest import MockEmbeddingModel


@pytest.mark.asyncio
async def test_integration_auto_rag_context_injection(tmp_path: Path):
    """
    Интеграционный тест: "Входящее сообщение -> Векторный поиск -> Контекст".
    Проверяет, что при упоминании определенных слов, RAG система автоматически
    подтягивает факты из БД и встраивает их в Markdown для LLM.
    """
    
    # 1. Поднимаем реальную Векторную БД во временной папке
    db_path = tmp_path / "qdrant_test"
    db = VectorDB(db_path=str(db_path), collections=["knowledge", "thoughts"], vector_size=3)
    await db.connect()

    mock_emb = MockEmbeddingModel()
    
    # 2. Инициализируем контроллеры знаний и мыслей
    col_know = VectorCollection(db, "knowledge")
    knowledge = VectorKnowledge(db, mock_emb, col_know, similarity_threshold=0.5)
    
    col_thou = VectorCollection(db, "thoughts")
    thoughts = VectorThoughts(db, mock_emb, col_thou, similarity_threshold=0.5)

    # 3. Агент когда-то давно сохранил важный факт в базу
    # Наш MockEmbeddingModel выдает вектор [1.0, 0.0, 0.0] на слово "яблоко"
    await knowledge.save_knowledge("Секретный код от яблока: 4242", tags=["type:fact"])
    
    # 4. Настраиваем Auto-RAG (Имитируем стейты)
    telethon_state = MagicMock()
    telethon_state.last_chats = ""
    agent_state = AgentState(current_step=1) # Первый шаг цикла (идет анализ входящего ивента)
    
    rag = RAGMemories(
        vector_knowledge=knowledge,
        vector_thoughts=thoughts,
        telethon_state=telethon_state,
        agent_state=agent_state,
        auto_rag_top_k=2
    )

    # 5. Имитируем входящее сообщение от пользователя
    payload = {
        "sender_name": "Boss",
        "message": "Агент, напомни, какой у нас пароль от яблока?",
        "raw_text": "Агент, напомни, какой у нас пароль от яблока?"
    }

    # 6. Прогоняем RAG-сборщик
    context_block = await rag.get_context_block(payload=payload, missed_events=[])

    # 7. Проверяем, что факт был "вспомнен" и добавлен в промпт
    assert "RELEVANT INFORMATION" in context_block
    assert "Секретный код от яблока: 4242" in context_block
    assert "type:fact" in context_block

    await db.disconnect()